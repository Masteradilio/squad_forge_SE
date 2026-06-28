from collections.abc import AsyncIterator
from typing import Any

import httpx

from localforge.llm.base import LLMConnectionError, LLMError, LLMTimeoutError
from localforge.llm.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider for the paid Chief Engineer model tier."""

    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str | None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        if not api_key:
            raise LLMError(
                "OpenRouter API key is required when Chief Engineer execution is requested."
            )
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
        )

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 240.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        model_name = model or self.default_model
        if not model_name:
            raise LLMError("OpenRouter model is required for Chief Engineer calls.")
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
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        if stream:
            return self._stream_chat_completion(url, headers, payload, timeout)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise LLMError(
                        f"OpenRouter completion failed ({resp.status_code}): "
                        f"{self._redact(resp.text)}"
                    )
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    raise LLMError("OpenRouter response did not contain completion choices.")
                return str(choices[0]["message"]["content"])
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"OpenRouter call timed out after {timeout}s") from e
        except httpx.RequestError as e:
            raise LLMConnectionError(f"OpenRouter call failed: {self._redact(str(e))}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"Unexpected OpenRouter error: {self._redact(str(e))}") from e

    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "[redacted]")
