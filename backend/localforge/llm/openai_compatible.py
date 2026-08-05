import json
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from localforge.llm.base import (
    BaseLLMProvider,
    LLMConnectionError,
    LLMError,
    LLMHTTPError,
    LLMMessage,
    LLMTimeoutError,
)

_UPSTREAM_ERROR_HINTS = (
    "model unavailable",
    "model cannot process this request",
    "engine unavailable",
    "service temporarily unavailable",
    "context length",
    "tokens exceed",
    "context_window",
)


def _looks_like_upstream_error(content: str) -> bool:
    """Return True if ``content`` looks like an error payload instead of
    a real assistant message.

    Several free-tier inference providers (notably NVIDIA NIM with
    Minimax-M3 when ``response_format=json_object`` is requested)
    return ``HTTP 200`` with the error message embedded as the
    assistant ``content``. Treating that as a normal answer routes it
    into the schema validator and yields repeated ``ValidationError``s
    that never recover. Detect that pattern early."""
    if not content:
        return False
    lowered = content.strip().lower()
    if not lowered:
        return False
    if lowered.startswith('{"error"'):
        return True
    return any(hint in lowered for hint in _UPSTREAM_ERROR_HINTS)


def decode_chat_completion_response(response: httpx.Response) -> str:
    """Decode a normal OpenAI response or an SSE response sent for ``stream=false``.

    Some OpenAI-compatible gateways always emit SSE frames, even when the
    request disables streaming. Normalizing both wire formats here keeps the
    local provider and gateway-specific clients on the same contract.
    """
    body = response.text if isinstance(response.text, str) else ""
    if body.lstrip().startswith("data:") or "text/event-stream" in response.headers.get(
        "content-type", ""
    ).lower():
        parts: list[str] = []
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            data_str = line.removeprefix("data:").strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta", {})
            content = delta.get("content") if isinstance(delta, dict) else None
            if content is None:
                message = choice.get("message", {})
                content = message.get("content") if isinstance(message, dict) else None
            if content:
                parts.append(str(content))
        if parts:
            return "".join(parts)

    data = response.json()
    choices = data.get("choices", [])
    if not choices:
        raise LLMError("API response did not contain completion choices.")
    content = choices[0].get("message", {}).get("content") or ""
    if not isinstance(content, str):
        raise LLMError("API response completion content was not text.")
    return content


def _ollama_options_overrides() -> dict[str, object]:
    """Read Ollama runtime overrides from the environment.

    LOCALFORGE_LLM_NUM_CTX (int, recommended >= 32768): maps to the
    Ollama ``options.num_ctx`` request field, which controls the model's
    effective context window. The default Ollama server hands out
    2 KiB unless overridden, which silently caps the local lanes and
    forces the squad to fall back to paid APIs for tasks the local
    host is fully capable of handling. LocalForge deliberately leaves
    this opt-in: operators are expected to set the value to match the
    model's supported context window (gemma4:12b → 262144,
    granite4.1:8b → 131072, nemotron-3-nano:4b → 4096).
    """
    options: dict[str, object] = {}
    raw = os.getenv("LOCALFORGE_LLM_NUM_CTX")
    if not raw:
        return options
    try:
        options["num_ctx"] = int(raw)
    except ValueError:
        return options
    return options


class OpenAICompatibleProvider(BaseLLMProvider):
    """LLM provider wrapper using OpenAI-compatible API schemas (e.g.

    Ollama /v1, vLLM, OpenAI).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        default_model: str | None = None,
        provider_name: str = "openai_compatible",
        max_output_tokens: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        gateway_key = os.getenv("OMNIROUTE_API_KEY") if provider_name.lower() == "omniroute" else None
        self.api_key = (
            api_key
            or os.getenv("LOCALFORGE_MODEL_API_KEY")
            or gateway_key
            or "no-key"
        )
        self.default_model = default_model
        self.provider_name = provider_name
        # Honour ``LOCALFORGE_LLM_MAX_OUTPUT_TOKENS`` (and the
        # ``LOCALFORGE_LLM_MAX_INPUT_TOKENS`` companion). Operators with
        # free-tier NVIDIA / OpenRouter keys regularly hit ``max_tokens``
        # truncation that collapses otherwise valid JSON Schema responses
        # into ``content: null``; the default of 0 means "let the
        # provider decide", which is fine but easy to misjudge.
        if max_output_tokens is not None:
            self.default_max_output_tokens = max_output_tokens
        else:
            try:
                self.default_max_output_tokens = int(
                    os.getenv("LOCALFORGE_LLM_MAX_OUTPUT_TOKENS", "0") or "0"
                )
            except ValueError:
                self.default_max_output_tokens = 0
        try:
            self.default_max_input_tokens = int(
                os.getenv("LOCALFORGE_LLM_MAX_INPUT_TOKENS", "0") or "0"
            )
        except ValueError:
            self.default_max_input_tokens = 0

    async def list_models(self) -> list[str]:
        """Fetch active models using the GET /v1/models endpoint."""
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    raise LLMHTTPError(
                        f"HTTP Error {resp.status_code}: {resp.text}",
                        status_code=resp.status_code,
                    )
                data = resp.json()
                # Parse list format
                items = data.get("data", [])
                return [item["id"] for item in items if "id" in item]
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"Connection timeout to {url}") from e
        except httpx.RequestError as e:
            raise LLMConnectionError(f"Failed to connect to {url}: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"Unexpected error listing models: {e}") from e

    async def chat_completion(
        self,
        messages: list[LLMMessage],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 240.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        """Execute chat completion request against POST /v1/chat/completions."""
        from localforge.llm.context import (
            check_and_increment_llm_calls,
            get_active_task_run_id,
            get_llm_limit,
        )

        task_run_id = get_active_task_run_id()
        if task_run_id is not None:
            from localforge.core.config import load_config

            try:
                config = load_config()
                default_limit = config.budgets.max_active_model_calls
            except Exception:
                default_limit = 4
            limit = get_llm_limit(task_run_id, default_limit)
            await check_and_increment_llm_calls(task_run_id, limit)

        model_name = model or self.default_model
        if not model_name:
            raise LLMError("No model name configured or supplied in request.")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
        }
        # Operator-tunable output token ceiling. We default to letting
        # the remote side decide (``0`` means "omit max_tokens") so the
        # existing tests keep their behaviour, but a positive env value
        # unlocks the full output budget the configured model can emit.
        if self.default_max_output_tokens > 0:
            max_output_tokens = self.default_max_output_tokens
            if self.provider_name.lower() == "omniroute":
                # Free/freemium OmniRoute routes can spend an unbounded amount
                # of time in hidden reasoning when given the 8k Chief ceiling.
                # ForgeOS actions and plain visual documents are both bounded;
                # cap every OmniRoute transport so a free route cannot spend
                # an unbounded time generating a large response.
                try:
                    gateway_cap = int(
                        os.getenv("LOCALFORGE_OMNIROUTE_MAX_OUTPUT_TOKENS", "6000")
                    )
                except ValueError:
                    gateway_cap = 6000
                if gateway_cap > 0:
                    max_output_tokens = min(max_output_tokens, gateway_cap)
            payload["max_tokens"] = max_output_tokens

        # OmniRoute's free/freemium routes may emit hidden reasoning before
        # the answer. Keep that reasoning deliberately low for every ForgeOS
        # request, including plain HTML transport used by visual tasks;
        # otherwise a complete document can time out before its source is
        # emitted. OmniRoute accepts this field, while other providers must
        # not see it.
        if self.provider_name.lower() == "omniroute":
            reasoning_effort = os.getenv("LOCALFORGE_OMNIROUTE_REASONING_EFFORT", "none").strip()
            if reasoning_effort in {"none", "minimal", "low", "medium", "high"}:
                payload["reasoning_effort"] = reasoning_effort

        # Request JSON output format; the Ollama host ignores this flag
        # (it always answers with plain JSON content) while NIM/vLLM
        # honour it, so the backend normalisation happens here.
        if response_schema is not None and self.provider_name.lower() != "omniroute":
            payload["response_format"] = {"type": "json_object"}
        # Forward Ollama-specific runtime options (currently only
        # num_ctx, the model's effective context window). We key them
        # under "options" to match the Ollama /v1 API the way the
        # upstream Ollama server expects when called with raw JSON
        # instead of the ``-d`` shell wrapper.
        ollama_options = _ollama_options_overrides()
        if ollama_options and (self.provider_name or "").lower().startswith("ollama"):
            payload["options"] = ollama_options
        if stream:
            return self._stream_chat_completion(url, headers, payload, timeout)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise LLMHTTPError(
                        f"Completion API failed ({resp.status_code}): {resp.text}",
                        status_code=resp.status_code,
                    )
                content = decode_chat_completion_response(resp)
                # Detect upstream-model errors hidden inside the first choice.
                # than as an HTTP 4xx/5xx. Treating that as a normal
                # content would route it into the validator, where every
                # subsequent retry then has to fail in JSON parse-or-
                # schema-validate before the operator notices. Surface it
                # as a distinct, retryable LLMError so the wrapper or the
                # fall-through provider can skip the model.
                if _looks_like_upstream_error(content):
                    raise LLMError(
                        f"Upstream model error returned inside content: {content[:300]!r}"
                    )
                return str(content)
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"Chat completion call timed out after {timeout}s") from e
        except httpx.RequestError as e:
            raise LLMConnectionError(f"Chat completion call failed: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"Unexpected error in chat completion: {e}") from e

    async def _stream_chat_completion(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[str]:
        """Private generator for streaming chat completions chunk by chunk."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise LLMHTTPError(
                            f"Streaming request failed ({response.status_code}): {body.decode()}",
                            status_code=response.status_code,
                        )

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                # OmniRoute may report upstream quota and
                                # provider failures as SSE JSON frames while
                                # keeping the HTTP response at 200. Do not
                                # discard those frames and wait for the
                                # structured-output timeout.
                                error_payload = chunk_data.get("error")
                                if isinstance(error_payload, dict):
                                    message = error_payload.get("message") or error_payload
                                    code = error_payload.get("code")
                                    suffix = f" ({code})" if code else ""
                                    raise LLMError(
                                        f"Streaming upstream error{suffix}: {message}"
                                    )
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except Exception as exc:
                                if isinstance(exc, LLMError):
                                    raise
                                # Ignore malformed non-data SSE frames; the
                                # provider error path above remains fatal.
                                pass
        except httpx.TimeoutException as e:
            raise LLMTimeoutError("Streaming connection timed out") from e
        except httpx.RequestError as e:
            raise LLMConnectionError(f"Streaming network error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"Unexpected error in streaming: {e}") from e
