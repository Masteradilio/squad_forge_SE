from localforge.core.config import LocalForgeConfig
from localforge.llm.base import BaseLLMProvider, LLMError
from localforge.llm.openai_compatible import OpenAICompatibleProvider


def build_chief_engineer_provider(config: LocalForgeConfig) -> BaseLLMProvider:
    """Build the configured Chief Engineer provider without pipeline coupling."""
    chief = config.chief_engineer
    provider_name = chief.provider.lower()
    if provider_name in {"omniroute", "omni_route"}:
        return OpenAICompatibleProvider(
            base_url=chief.base_url,
            api_key=chief.api_key,
            default_model=chief.model,
            provider_name="omniroute",
            max_output_tokens=chief.max_output_tokens_per_call,
        )
    raise LLMError(
        "ForgeOS Cloud requires the Chief Engineer to use OmniRoute; "
        f"direct provider '{chief.provider}' is not allowed."
    )
