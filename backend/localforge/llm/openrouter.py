from localforge.llm.base import LLMError
from localforge.llm.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider for the paid Chief Engineer model tier."""

    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str | None,
        base_url: str = "https://openrouter.ai/api/v1",
        max_output_tokens: int | None = None,
    ):
        if not api_key:
            raise LLMError(
                "OpenRouter API key is required when Chief Engineer execution is requested."
            )
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            provider_name="openrouter",
            max_output_tokens=max_output_tokens,
        )
