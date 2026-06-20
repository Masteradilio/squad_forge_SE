from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMError(Exception):
    """Base exception for all LLM provider errors."""

    pass


class LLMConnectionError(LLMError):
    """Raised when the LLM provider endpoint is unreachable or returns a network error."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when the request to the LLM provider times out."""

    pass


class BaseLLMProvider(ABC):
    """Abstract base class defining LLM provider interfaces."""

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Retrieve list of available model names from the provider."""
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
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
