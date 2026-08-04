from collections.abc import AsyncIterator
from typing import Any

from localforge.llm.base import (
    BaseLLMProvider,
    LLMConnectionError,
    LLMError,
    LLMHTTPError,
    LLMMessage,
    LLMTimeoutError,
)


def _has_image_attachment(messages: list[LLMMessage]) -> bool:
    """Detect multimodal requests before choosing a provider fallback.

    A fallback route is not automatically entitled to receive image payloads:
    its vision capability must be verified separately. Keeping the visual
    request on the primary provider lets the Chief Engineer's bounded text
    contract fallback handle a capability or timeout failure without silently
    sending the same paid image request to an unverified provider.
    """

    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if any(
            isinstance(block, dict)
            and block.get("type") in {"image_url", "input_image"}
            for block in content
        ):
            return True
    return False


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
        messages: list[LLMMessage],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 240.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        multimodal = _has_image_attachment(messages)
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
        except (LLMConnectionError, LLMTimeoutError):
            if multimodal:
                raise
            return await self._call_fallback(messages, response_schema, stream, timeout)
        except LLMHTTPError as exc:
            # A 404 from a provider usually means that the configured model
            # is not available on that provider.  It is recoverable through
            # the configured provider fallback, unlike auth or billing
            # failures (401/402/403), which must remain visible.
            if exc.status_code not in {404, 429} and exc.status_code < 500:
                raise
            if multimodal:
                raise
            return await self._call_fallback(messages, response_schema, stream, timeout)
        except LLMError as exc:
            # Fallback when the upstream provider explicitly refused the
            # request by hiding the error message inside a 200 response
            # (NVIDIA NIM with response_format=json_object returns this
            # pattern for some free-tier models). Without this branch,
            # every retry repeats against the same broken endpoint until
            # the absolute recovery budget in the scheduler is exhausted.
            message = str(exc).lower()
            upstream_hint = (
                "upstream model error",
                "model unavailable",
                "model cannot process",
                "engine unavailable",
                "service temporarily unavailable",
            )
            if any(hint in message for hint in upstream_hint) and not multimodal:
                return await self._call_fallback(messages, response_schema, stream, timeout)
            raise

    async def _call_fallback(
        self,
        messages: list[LLMMessage],
        response_schema: dict[str, Any] | None,
        stream: bool,
        timeout: float,
    ) -> str | AsyncIterator[str]:
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
