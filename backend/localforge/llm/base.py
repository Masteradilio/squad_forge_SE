import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

LLMMessage = dict[str, Any]


class LLMError(Exception):
    """Base exception for all LLM provider errors."""

    pass


class LLMConnectionError(LLMError):
    """Raised when the LLM provider endpoint is unreachable or returns a network error."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when the request to the LLM provider times out."""

    pass


class LLMHTTPError(LLMError):
    """Raised when a provider returns a non-success HTTP response."""

    def __init__(self, message: str, *, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def is_permanent_provider_error(message: str) -> bool:
    """Return whether retrying the provider can succeed without operator action.

    Billing and authentication failures are not transient model failures. The
    scheduler uses this same classifier as the pipeline so a provider error is
    preserved across the task boundary instead of being retried as a generic
    implementation failure.
    """
    normalized = message.lower()
    if any(
        marker in normalized
        for marker in (
            "429",
            "rate limit",
            "timed out",
            "timeout",
            "temporarily unavailable",
        )
    ):
        return False
    return (
        bool(re.search(r"\b(?:401|402|403)\b", normalized))
        or "insufficient credits" in normalized
        or "billing limit" in normalized
        or "api key is invalid" in normalized
        or "authentication failed" in normalized
    )


class BaseLLMProvider(ABC):
    """Abstract base class defining LLM provider interfaces."""

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Retrieve list of available model names from the provider."""
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[LLMMessage],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        """Execute a chat completion request.

        If response_schema is provided, requests structured output format (JSON).
        Returns a string for standard completions, or an AsyncIterator for streaming.
        """
        pass
