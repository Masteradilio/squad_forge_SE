import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


@dataclass
class _ProviderCircuit:
    failures: int = 0
    opened_until: datetime | None = None


_PROVIDER_CIRCUITS: dict[str, _ProviderCircuit] = {}


def _provider_circuit_key(provider: BaseLLMProvider) -> str:
    provider_name = str(getattr(provider, "provider_name", "primary"))
    base_url = getattr(provider, "base_url", None)
    model = getattr(provider, "default_model", None)
    if not isinstance(base_url, str):
        return f"{provider_name}:instance:{id(provider)}"
    return f"{provider_name}:{base_url}:{model or ''}"


def _provider_circuit_settings() -> tuple[int, float]:
    try:
        threshold = max(1, int(os.getenv("LOCALFORGE_PROVIDER_FAILURE_THRESHOLD", "2")))
    except ValueError:
        threshold = 2
    try:
        cooldown = min(
            900.0,
            max(5.0, float(os.getenv("LOCALFORGE_PROVIDER_COOLDOWN_SECONDS", "60"))),
        )
    except ValueError:
        cooldown = 60.0
    return threshold, cooldown


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
        self._circuit_key = _provider_circuit_key(primary)
        self.primary_failure_reason: str | None = None

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
        circuit = _PROVIDER_CIRCUITS.setdefault(self._circuit_key, _ProviderCircuit())
        now = datetime.now(UTC)
        if circuit.opened_until and now < circuit.opened_until:
            self.primary_failure_reason = (
                f"primary circuit open until {circuit.opened_until.isoformat()}"
            )
            if multimodal:
                raise LLMConnectionError(
                    "Primary provider circuit is open and no verified multimodal fallback is configured."
                )
            return await self._call_fallback(messages, response_schema, stream, timeout)
        if circuit.opened_until and now >= circuit.opened_until:
            circuit.opened_until = None
        try:
            self.last_provider_name = str(getattr(self.primary, "provider_name", "primary"))
            self.provider_name = self.last_provider_name
            self.used_fallback = False
            result = await self.primary.chat_completion(
                messages,
                response_schema=response_schema,
                stream=stream,
                timeout=min(timeout, self.primary_timeout),
                model=model,
            )
            circuit.failures = 0
            self.primary_failure_reason = None
            return result
        except (LLMConnectionError, LLMTimeoutError):
            self._record_primary_failure(circuit, "transport or timeout")
            if multimodal:
                raise
            return await self._call_fallback(messages, response_schema, stream, timeout)
        except LLMHTTPError as exc:
            # A missing model (404), authentication, billing, validation, or
            # configuration response must remain visible. Only rate limits
            # and provider-side failures are safe to retry elsewhere.
            if exc.status_code != 429 and exc.status_code < 500:
                raise
            self._record_primary_failure(circuit, f"http {exc.status_code}")
            if multimodal:
                raise
            return await self._call_fallback(messages, response_schema, stream, timeout)
        except LLMError as exc:
            # Some gateways hide a transient upstream outage inside a 200
            # response. Do not treat model/configuration/schema errors as a
            # routing failure: those require changing the task or settings.
            message = str(exc).lower()
            upstream_hint = (
                "service temporarily unavailable",
                "upstream service unavailable",
                "upstream gateway unavailable",
            )
            if any(hint in message for hint in upstream_hint) and not multimodal:
                self._record_primary_failure(circuit, "transient upstream service error")
                return await self._call_fallback(messages, response_schema, stream, timeout)
            raise

    def _record_primary_failure(self, circuit: _ProviderCircuit, reason: str) -> None:
        circuit.failures += 1
        self.primary_failure_reason = reason
        threshold, cooldown_seconds = _provider_circuit_settings()
        if circuit.failures >= threshold:
            circuit.opened_until = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)

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
