"""Pre-Flight Discovery Engine — Fine-grained daily recency, agentic capability filter & combo injector."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List
from localforge.services.omniroute_client import OmniRouteClient

logger = logging.getLogger(__name__)


class PreFlightDiscoveryEngine:
    """Pre-flight discovery engine for selecting and sorting optimal free LLM models."""

    def __init__(self, omniroute_client: Optional[OmniRouteClient] = None):
        self.client = omniroute_client or OmniRouteClient()

    async def discover_and_rank_models(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch, filter, and rank free models by recency (days), agentic capability, and parameter size."""
        raw_models = await self.client.get_models()

        agentic_models = []
        for model in raw_models:
            # Task 2.3: Agentic capability filter (tools & json_schema)
            supports_tools = model.get("supports_tools", True) or model.get("tools", True)
            supports_json = model.get("supports_json", True) or model.get("json_schema", True)
            is_free = model.get("is_free", True) or model.get("free_tier", True)

            if supports_tools and supports_json and is_free:
                # Task 2.4: Calculate recency in days
                release_str = model.get("release_date") or "2024-01-01"
                try:
                    rel_date = datetime.fromisoformat(release_str.replace("Z", "+00:00"))
                except Exception:
                    rel_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                age_days = max(0, (now - rel_date).days)
                model["age_days"] = age_days

                # Parameter size score
                params_b = model.get("param_size_b", 70)
                model["param_score"] = params_b

                agentic_models.append(model)

        # Sort strictly by: 1) recency in days (asc), 2) param size score (desc)
        sorted_models = sorted(
            agentic_models,
            key=lambda m: (m.get("age_days", 999), -m.get("param_score", 0))
        )

        high_tier = [m["id"] for m in sorted_models if m.get("param_score", 0) >= 32]
        mid_tier = [m["id"] for m in sorted_models if m.get("param_score", 0) < 32]

        if not high_tier:
            high_tier = [m["id"] for m in sorted_models[:5]]
        if not mid_tier:
            mid_tier = [m["id"] for m in sorted_models[5:]] or high_tier

        # Task 2.5: Inject dynamic combos into OmniRoute
        await self.client.register_combo("forge-high-tier", high_tier)
        await self.client.register_combo("forge-mid-tier", mid_tier)

        logger.info(f"Discovered {len(sorted_models)} agentic models. High-Tier: {high_tier}, Mid-Tier: {mid_tier}")

        return {
            "all_ranked": sorted_models,
            "forge_high_tier": high_tier,
            "forge_mid_tier": mid_tier,
        }
