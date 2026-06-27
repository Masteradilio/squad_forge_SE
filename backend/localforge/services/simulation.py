from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from localforge.storage.orm import ModelCallLedgerORM, ModelPricingSnapshotORM
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason


class APISimulationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def simulate_api_only_costs(
        self,
        project_id: int,
        run_id: int | None = None
    ) -> dict[str, Any]:
        """
        Simulates what the runs would have cost under 100% API execution.
        Compares OpenAI, Anthropic, and Google baseline pricing models.
        """
        # 1. Fetch all calls
        stmt = select(ModelCallLedgerORM).where(ModelCallLedgerORM.project_id == project_id)
        if run_id is not None:
            stmt = stmt.where(ModelCallLedgerORM.run_id == run_id)
        res = await self.session.execute(stmt)
        calls = res.scalars().all()

        # 2. Fetch pricing snapshots from DB
        snap_res = await self.session.execute(select(ModelPricingSnapshotORM))
        snapshots = {s.model_name: s for s in snap_res.scalars().all()}

        # 3. Mappings for models per provider
        provider_map = {
            "OpenAI": {
                "large": "gpt-5.5-large",
                "medium": "gpt-5.4-medium",
                "small": "gpt-5.4-mini"
            },
            "Anthropic": {
                "large": "claude-opus-4.8",
                "medium": "claude-sonnet-4.6",
                "small": "claude-haiku-4.5"
            },
            "Google": {
                "large": "gemini-2.5-pro",
                "medium": "gemini-2.5-flash",
                "small": "gemini-2.5-flash-lite"
            }
        }

        # Fallback pricing in case DB is not fully seeded or populated
        fallbacks = {
            "gpt-5.5-large": (5.0, 30.0),
            "gpt-5.4-medium": (2.50, 15.00),
            "gpt-5.4-mini": (0.75, 4.50),
            "claude-opus-4.8": (5.0, 25.0),
            "claude-sonnet-4.6": (3.0, 15.0),
            "claude-haiku-4.5": (1.0, 5.0),
            "gemini-2.5-pro": (1.25, 10.0),
            "gemini-2.5-flash": (0.30, 2.50),
            "gemini-2.5-flash-lite": (0.10, 0.40)
        }

        def get_prices(model_name: str) -> tuple[float, float]:
            if model_name in snapshots:
                return snapshots[model_name].input_price_per_million, snapshots[model_name].output_price_per_million
            return fallbacks.get(model_name, (1.0, 1.0))

        actual_paid = 0.0
        openai_sim = 0.0
        anthropic_sim = 0.0
        google_sim = 0.0

        for call in calls:
            input_tokens = call.input_tokens
            output_tokens = call.output_tokens

            # Map tier
            is_chief = call.provider == "openrouter" or "chief" in call.reason.lower() or "contract" in call.reason.lower() or "repair" in call.reason.lower() or "review" in call.reason.lower()
            is_small = "pr" in call.reason.lower() or "summary" in call.reason.lower() or "changelog" in call.reason.lower()
            tier = "large" if is_chief else ("small" if is_small else "medium")

            # OpenAI Simulation
            op_in, op_out = get_prices(provider_map["OpenAI"][tier])
            openai_sim += (input_tokens * op_in + output_tokens * op_out) / 1_000_000

            # Anthropic Simulation
            ant_in, ant_out = get_prices(provider_map["Anthropic"][tier])
            anthropic_sim += (input_tokens * ant_in + output_tokens * ant_out) / 1_000_000

            # Google Simulation
            gg_in, gg_out = get_prices(provider_map["Google"][tier])
            google_sim += (input_tokens * gg_in + output_tokens * gg_out) / 1_000_000

            if call.provider == "openrouter":
                actual_paid += call.estimated_cost_usd

        return {
            "actual_paid_usd": actual_paid,
            "openai_simulated_usd": openai_sim,
            "anthropic_simulated_usd": anthropic_sim,
            "google_simulated_usd": google_sim,
            "openai_savings_usd": max(0.0, openai_sim - actual_paid),
            "anthropic_savings_usd": max(0.0, anthropic_sim - actual_paid),
            "google_savings_usd": max(0.0, google_sim - actual_paid),
            "total_calls": len(calls),
        }
