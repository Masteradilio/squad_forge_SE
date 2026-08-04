from localforge.llm.base import LLMError
from localforge.llm.openai_compatible import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):
    """NVIDIA NIM OpenAI-compatible provider for Chief Engineer calls."""

    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str | None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        max_output_tokens: int | None = None,
    ):
        if not api_key:
            raise LLMError("NVIDIA API key is required for NVIDIA Chief Engineer calls.")
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            provider_name="nvidia",
            max_output_tokens=max_output_tokens,
        )
