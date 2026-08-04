"""Pre-Flight Discovery Engine — Fine-grained daily recency, agentic capability filter & combo injector."""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from localforge.services.omniroute_client import OmniRouteClient
from localforge.services.pricing import is_free_gateway_model

logger = logging.getLogger(__name__)

FREEMIUM_GATEWAY_ROUTES = (
    "auto/best-free",
    "auto/coding:free",
    "oc/nemotron-3-ultra-free",
    "oc/mimo-v2.5-free",
    "oc/north-mini-code-free",
)


class PreFlightDiscoveryEngine:
    """Pre-flight discovery engine for selecting and sorting optimal free LLM models."""

    def __init__(self, omniroute_client: OmniRouteClient | None = None):
        self.client = omniroute_client or OmniRouteClient()

    async def discover_and_rank_models(self) -> dict[str, list[Any]]:
        """Fetch, filter, and rank free models by recency (days), agentic capability, and parameter size."""
        raw_models = await self.client.get_models()

        # Catalog metadata is advisory. Probe concrete freemium routes and keep
        # only routes that currently satisfy both structured-output and tool-use
        # contracts. Stop after four healthy routes to bound pre-flight latency.
        catalog_ids = {
            str(model.get("id")) for model in raw_models if isinstance(model.get("id"), str)
        }
        verified_gateway_routes: set[str] = set()
        verified_route_order: list[str] = []
        if getattr(self.client, "gateway_json_contract_verified", False):
            verify_agentic = getattr(self.client, "verify_agentic_contract", None)
            verify_json = getattr(self.client, "verify_json_contract", None)
            catalog_free_routes = [
                model_id
                for model_id in catalog_ids
                if is_free_gateway_model(model_id)
            ]
            route_candidates = list(
                dict.fromkeys(
                    [
                        *[route for route in FREEMIUM_GATEWAY_ROUTES if route in catalog_ids],
                        *sorted(catalog_free_routes),
                    ]
                )
            )
            try:
                max_route_probes = min(
                    12,
                    max(1, int(os.getenv("LOCALFORGE_OMNIROUTE_MAX_ROUTE_PROBES", "6"))),
                )
            except ValueError:
                max_route_probes = 6
            for route in route_candidates[:max_route_probes]:
                if callable(verify_agentic):
                    verified = await verify_agentic(route)
                elif callable(verify_json):
                    try:
                        verified = await verify_json(route)
                    except TypeError:
                        verified = await verify_json()
                else:
                    verified = False
                if verified:
                    verified_gateway_routes.add(route)
                    verified_route_order.append(route)
                if len(verified_gateway_routes) >= 4:
                    break
            if not verified_gateway_routes:
                raise RuntimeError("OmniRoute failed its live agentic contract verification")

        agentic_models: list[dict[str, Any]] = []
        for model in raw_models:
            # Task 2.3: Agentic capability filter (tools & json_schema)
            # Missing metadata is unknown, not an implicit approval.  Discovery
            # must never route an agent to a model that did not declare the
            # capabilities required by its contract.
            capabilities = model.get("capabilities")
            capability_map = capabilities if isinstance(capabilities, dict) else {}
            supported_parameters = model.get("supported_parameters")
            supported_parameter_names = (
                {str(value).lower() for value in supported_parameters}
                if isinstance(supported_parameters, list)
                else set()
            )
            supports_tools = bool(
                model.get(
                    "supports_tools",
                    model.get(
                        "supports_tool_calling",
                        model.get(
                            "tools",
                            capability_map.get(
                                "tools", capability_map.get("tool_calling", False)
                            ),
                        ),
                    ),
                )
            ) or "tools" in supported_parameter_names
            model_id = model.get("id")
            gateway_combo = (
                isinstance(model_id, str)
                and model_id.startswith("auto/")
                and str(model.get("owned_by", "")).lower() == "combo"
            )
            supports_json = bool(
                model.get(
                    "supports_json",
                    model.get(
                        "supports_json_schema",
                        model.get("json_schema", capability_map.get("json_schema", False)),
                    ),
                )
            ) or bool(
                {"response_format", "json_schema", "structured_outputs"}
                & supported_parameter_names
            )
            if gateway_combo and bool(
                getattr(self.client, "gateway_json_contract_verified", False)
            ):
                supports_json = str(model_id) in verified_gateway_routes
            pricing = model.get("pricing")
            pricing_is_free = isinstance(pricing, dict) and all(
                str(pricing.get(key, "")) in {"0", "0.0", "0.00"}
                for key in ("prompt", "completion")
            )
            is_free = bool(
                model.get("is_free", model.get("free_tier", pricing_is_free))
            ) or is_free_gateway_model(model_id if isinstance(model_id, str) else None)
            # Built-in ``auto/*free`` routes are gateway-managed free-tier
            # aliases. Other auto routes remain excluded unless the catalog
            # provides an explicit free/pricing declaration.
            if gateway_combo and str(model_id) in verified_gateway_routes:
                is_free = True

            if supports_tools and supports_json and is_free and isinstance(model_id, str) and model_id:
                # Task 2.4: Calculate recency in days
                release_str = model.get("release_date") or model.get("updated_at") or "2024-01-01"
                try:
                    rel_date = datetime.fromisoformat(release_str.replace("Z", "+00:00"))
                    if rel_date.tzinfo is None:
                        rel_date = rel_date.replace(tzinfo=UTC)
                except Exception:
                    rel_date = datetime(2024, 1, 1, tzinfo=UTC)

                now = datetime.now(UTC)
                age_days = max(0, (now - rel_date).days)
                model["age_days"] = age_days

                # Parameter size score
                params_b = model.get("param_size_b", model.get("parameter_size_b", 0))
                model["param_score"] = float(params_b) if isinstance(params_b, (int, float)) else 0.0

                agentic_models.append(model)

        # Sort strictly by: 1) recency in days (asc), 2) param size score (desc)
        sorted_models = sorted(
            agentic_models,
            key=lambda m: (m.get("age_days", 999), -m.get("param_score", 0))
        )

        high_tier = [m["id"] for m in sorted_models if m.get("param_score", 0) >= 32]
        mid_tier = [m["id"] for m in sorted_models if m.get("param_score", 0) < 32]

        if verified_gateway_routes:
            verified_free_routes = verified_route_order
            # Free routes do not publish parameter sizes consistently. Keep
            # the tiers deterministic without introducing paid aliases.
            high_tier = verified_free_routes[:1]
            mid_tier = verified_free_routes[1:] or high_tier

        if not high_tier:
            high_tier = [m["id"] for m in sorted_models[:5]]
        if not mid_tier:
            mid_tier = [m["id"] for m in sorted_models[5:]] or high_tier
        fast_tier = [
            route
            for route in FREEMIUM_GATEWAY_ROUTES
            if route in verified_gateway_routes
        ] or mid_tier

        # Task 2.5: Inject dynamic combos only when the deployment explicitly
        # provisions a management credential. The stock gateway still exposes
        # stable ``auto/*free`` routes, so discovery can remain useful without
        # pretending that an unauthenticated management mutation succeeded.
        if getattr(self.client, "combo_mutation_enabled", True):
            if high_tier and not await self.client.register_combo("forge-high-tier", high_tier):
                raise RuntimeError("OmniRoute rejected the forge-high-tier combo registration")
            if mid_tier and not await self.client.register_combo("forge-mid-tier", mid_tier):
                raise RuntimeError("OmniRoute rejected the forge-mid-tier combo registration")
            if fast_tier and not await self.client.register_combo("forge-fast-tier", fast_tier):
                raise RuntimeError("OmniRoute rejected the forge-fast-tier combo registration")
        else:
            logger.info("OmniRoute combo mutation disabled; using verified gateway routes directly")

        logger.info(f"Discovered {len(sorted_models)} agentic models. High-Tier: {high_tier}, Mid-Tier: {mid_tier}")

        return {
            "all_ranked": sorted_models,
            "forge_high_tier": high_tier,
            "forge_mid_tier": mid_tier,
            "forge_fast_tier": fast_tier,
        }
