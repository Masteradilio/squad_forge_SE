"""Shared provider benchmark model mapping and strict snapshot resolution."""

from collections.abc import Mapping
from typing import Any

BASELINE_MODELS: dict[str, dict[str, str]] = {
    "OpenAI": {"large": "gpt-5.5-large", "medium": "gpt-5.4-medium", "small": "gpt-5.4-mini"},
    "Anthropic": {"large": "claude-opus-4.8", "medium": "claude-sonnet-4.6", "small": "claude-haiku-4.5"},
    "Google": {"large": "gemini-2.5-pro", "medium": "gemini-2.5-flash", "small": "gemini-2.5-flash-lite"},
}

LOCAL_PROVIDERS = {"ollama", "local", "localforge", "omniroute", "omni_route"}
# OmniRoute calls are bounded independently from paid-provider budgets. Keep
# this finite default safe for callers that create a run without explicitly
# copying the configured resource limits into its Run record.
DEFAULT_MAX_GATEWAY_CALLS = 48


def is_gateway_provider(provider: str) -> bool:
    """Return whether the call crossed the ForgeOS OmniRoute gateway."""
    return provider.strip().lower() in {"omniroute", "omni_route"}


def is_free_gateway_model(model: str | None) -> bool:
    """Return whether an OmniRoute model identifier explicitly denotes free use."""
    if not model:
        return False
    normalized = model.strip().lower()
    return normalized.endswith(":free") or "-free" in normalized or "free/" in normalized


def is_billed_call(provider: str, estimated_cost_usd: float) -> bool:
    """Recognize billed gateway calls without confusing free routes with local work."""
    if is_gateway_provider(provider):
        return estimated_cost_usd > 0.0
    return is_paid_provider(provider)


def snapshot_prices(snapshots: Mapping[str, Any], model_name: str) -> tuple[float, float]:
    """Return prices from a persisted snapshot, never an invented fallback."""
    snapshot = snapshots.get(model_name)
    if snapshot is None:
        raise RuntimeError(
            f"Missing pricing snapshot for benchmark model {model_name!r}; "
            "refresh the pricing registry before generating a cost report."
        )
    return float(snapshot.input_price_per_million), float(snapshot.output_price_per_million)


def is_paid_provider(provider: str) -> bool:
    return provider.strip().lower() not in LOCAL_PROVIDERS
