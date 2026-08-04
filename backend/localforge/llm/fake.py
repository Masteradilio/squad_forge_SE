from collections.abc import AsyncIterator
from typing import Any

from localforge.llm.base import BaseLLMProvider, LLMMessage


class FakeLLMProvider(BaseLLMProvider):
    """Mock LLM Provider for local testing and deterministic responses."""

    def __init__(
        self,
        models: list[str] | None = None,
        responses: list[str] | None = None,
    ):
        self.models_list = models or ["llama3", "mistral"]
        self.responses = responses or []
        self.response_index = 0
        self.last_payload: dict[str, Any] = {}

    async def list_models(self) -> list[str]:
        return self.models_list

    async def chat_completion(
        self,
        messages: list[LLMMessage],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        self.last_payload = {
            "messages": messages,
            "response_schema": response_schema,
            "stream": stream,
            "timeout": timeout,
            "model": model,
        }

        if self.responses:
            res = self.responses[self.response_index % len(self.responses)]
            self.response_index += 1
        else:
            res = "Default mock completion."

        if stream:

            async def _stream() -> AsyncIterator[str]:
                for word in res.split():
                    yield word + " "

            return _stream()

        return res
