from localforge.core.config import LocalForgeConfig
from localforge.llm.base import BaseLLMProvider, LLMError
from localforge.llm.fallback import FallbackLLMProvider
from localforge.llm.nvidia import NvidiaProvider
from localforge.llm.openrouter import OpenRouterProvider


def build_chief_engineer_provider(config: LocalForgeConfig) -> BaseLLMProvider:
    """Build the configured Chief Engineer provider without pipeline coupling."""
    chief = config.chief_engineer
    provider_name = chief.provider.lower()
    if provider_name == "nvidia":
        primary = NvidiaProvider(
            api_key=chief.api_key,
            base_url=chief.base_url,
            default_model=chief.model,
        )
        if (
            chief.fallback_provider == "openrouter"
            and chief.fallback_model
            and chief.fallback_api_key
        ):
            fallback = OpenRouterProvider(
                api_key=chief.fallback_api_key,
                base_url=chief.fallback_base_url or "https://openrouter.ai/api/v1",
                default_model=chief.fallback_model,
            )
            return FallbackLLMProvider(
                primary=primary,
                fallback=fallback,
                primary_timeout=chief.fallback_after_seconds,
            )
        return primary
    if provider_name == "openrouter":
        return OpenRouterProvider(
            api_key=chief.api_key,
            base_url=chief.base_url,
            default_model=chief.model,
        )
    raise LLMError(f"Unsupported Chief Engineer provider: {chief.provider}")
