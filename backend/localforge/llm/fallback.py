from collections.abc import AsyncIterator
from typing import Any

from localforge.llm.base import BaseLLMProvider


class FallbackLLMProvider(BaseLLMProvider):
    """Try a primary provider first, then a fallback provider after a short timeout."""

    def __init__(
        self,
        *,
        primary: BaseLLMProvider,
        fallback: BaseLLMProvider,
        primary_timeout: float,
    ):
        self.primary = primary
        self.fallback = fallback
        self.primary_timeout = primary_timeout
        self.provider_name = str(getattr(primary, "provider_name", "primary"))
        self.default_model = getattr(primary, "default_model", None)
        self.last_provider_name = self.provider_name
        self.primary_provider_name = self.provider_name
        self.fallback_provider_name = str(getattr(fallback, "provider_name", "fallback"))
        self.used_fallback = False

    async def list_models(self) -> list[str]:
        return await self.primary.list_models()

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 240.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        try:
            self.last_provider_name = str(getattr(self.primary, "provider_name", "primary"))
            self.provider_name = self.last_provider_name
            self.used_fallback = False
            return await self.primary.chat_completion(
                messages,
                response_schema=response_schema,
                stream=stream,
                timeout=min(timeout, self.primary_timeout),
                model=model,
            )
        except Exception:
            self.last_provider_name = self.fallback_provider_name
            self.provider_name = self.last_provider_name
            self.used_fallback = True
            return await self.fallback.chat_completion(
                messages,
                response_schema=response_schema,
                stream=stream,
                timeout=timeout,
                model=getattr(self.fallback, "default_model", None),
            )
