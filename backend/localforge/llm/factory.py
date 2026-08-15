from localforge.core.config import (
    DEFAULT_NVIDIA_URL,
    DEFAULT_OPENROUTER_URL,
    LocalForgeConfig,
)
from localforge.llm.base import BaseLLMProvider, LLMError
from localforge.llm.fallback import FallbackLLMProvider
from localforge.llm.nvidia import NvidiaProvider
from localforge.llm.openai_compatible import OpenAICompatibleProvider
from localforge.llm.openrouter import OpenRouterProvider

DEFAULT_OMNIROUTE_URL = "http://localhost:20128/v1"


def _build_provider(
    *,
    provider_name: str,
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    max_output_tokens: int,
) -> BaseLLMProvider:
    if provider_name == "omniroute":
        return OpenAICompatibleProvider(
            base_url=base_url or DEFAULT_OMNIROUTE_URL,
            api_key=api_key,
            default_model=model,
            provider_name="omniroute",
            max_output_tokens=max_output_tokens,
        )
    if provider_name == "openrouter":
        return OpenRouterProvider(
            api_key=api_key,
            base_url=base_url or DEFAULT_OPENROUTER_URL,
            default_model=model,
            max_output_tokens=max_output_tokens,
        )
    if provider_name == "nvidia":
        return NvidiaProvider(
            api_key=api_key,
            base_url=base_url or DEFAULT_NVIDIA_URL,
            default_model=model,
            max_output_tokens=max_output_tokens,
        )
    raise LLMError(f"Unsupported Chief Engineer provider: {provider_name or 'unset'}")


def _build_route(route, *, max_output_tokens: int) -> BaseLLMProvider:
    provider_name = str(route.provider).strip().lower().replace("_", "")
    return _build_provider(
        provider_name=provider_name,
        base_url=_route_base_url(provider_name, route.base_url),
        api_key=route.api_key,
        model=route.model,
        max_output_tokens=max_output_tokens,
    )


def _route_identity(provider: BaseLLMProvider) -> tuple[str, str | None, str | None]:
    return (
        str(getattr(provider, "provider_name", "")).strip().lower(),
        getattr(provider, "base_url", None),
        getattr(provider, "default_model", None),
    )


def _route_base_url(provider_name: str, configured: str | None) -> str | None:
    """Avoid treating the OmniRoute default as a direct-provider endpoint."""
    if configured and not (
        provider_name != "omniroute" and configured == DEFAULT_OMNIROUTE_URL
    ):
        return configured
    return {
        "omniroute": DEFAULT_OMNIROUTE_URL,
        "openrouter": DEFAULT_OPENROUTER_URL,
        "nvidia": DEFAULT_NVIDIA_URL,
    }.get(provider_name)


def build_chief_engineer_provider(config: LocalForgeConfig) -> BaseLLMProvider:
    """Build the critical route followed by the configured free-provider ladder."""
    chief = config.chief_engineer
    provider_name = chief.provider.strip().lower().replace("_", "")
    primary = _build_provider(
        provider_name=provider_name,
        base_url=_route_base_url(provider_name, chief.base_url),
        api_key=chief.api_key,
        model=chief.model,
        max_output_tokens=chief.max_output_tokens_per_call,
    )

    chain: BaseLLMProvider = primary
    route_identities = {_route_identity(primary)}

    fallback_name = (chief.fallback_provider or "").strip().lower().replace("_", "")
    if fallback_name:
        fallback = _build_provider(
            provider_name=fallback_name,
            base_url=_route_base_url(fallback_name, chief.fallback_base_url),
            api_key=chief.fallback_api_key,
            model=chief.fallback_model,
            max_output_tokens=chief.max_output_tokens_per_call,
        )
        chain = FallbackLLMProvider(
            primary=chain,
            fallback=fallback,
            primary_timeout=chief.fallback_after_seconds,
        )
        route_identities.add(_route_identity(fallback))

    # The paid OpenRouter route remains the first attempt whenever it is the
    # configured critical lane. Free direct routes are only consulted after
    # that lane (and any explicit fallback) has a transient failure.
    for route in chief.fallback_routes:
        fallback = _build_route(
            route,
            max_output_tokens=chief.max_output_tokens_per_call,
        )
        identity = _route_identity(fallback)
        if identity in route_identities:
            continue
        chain = FallbackLLMProvider(
            primary=chain,
            fallback=fallback,
            primary_timeout=chief.fallback_after_seconds,
        )
        route_identities.add(identity)
    return chain


def build_free_provider_ladder(config: LocalForgeConfig) -> list[BaseLLMProvider]:
    """Build direct free routes for non-critical model work."""

    return [
        _build_route(route, max_output_tokens=config.chief_engineer.max_output_tokens_per_call)
        for route in config.models.fallback_routes
    ]
