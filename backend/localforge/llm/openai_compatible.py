import os
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from localforge.llm.base import BaseLLMProvider, LLMConnectionError, LLMError, LLMTimeoutError


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
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("LOCALFORGE_MODEL_API_KEY") or "no-key"
        self.default_model = default_model
        self.provider_name = provider_name

    async def list_models(self) -> list[str]:
        """Fetch active models using the GET /v1/models endpoint."""
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    raise LLMError(f"HTTP Error {resp.status_code}: {resp.text}")
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
        messages: list[dict[str, str]],
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
                default_limit = 50
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

        # Request JSON output format
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        if stream:
            return self._stream_chat_completion(url, headers, payload, timeout)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise LLMError(f"Completion API failed ({resp.status_code}): {resp.text}")
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    raise LLMError("API response did not contain completion choices.")
                return str(choices[0]["message"]["content"])
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
                        raise LLMError(
                            f"Streaming request failed ({response.status_code}): {body.decode()}"
                        )

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except Exception:
                                pass
        except httpx.TimeoutException as e:
            raise LLMTimeoutError("Streaming connection timed out") from e
        except httpx.RequestError as e:
            raise LLMConnectionError(f"Streaming network error: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"Unexpected error in streaming: {e}") from e
