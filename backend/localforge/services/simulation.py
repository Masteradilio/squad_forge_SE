from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.services.pricing import BASELINE_MODELS, is_billed_call, snapshot_prices
from localforge.storage.orm import ModelCallLedgerORM, ModelPricingSnapshotORM


class APISimulationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def simulate_api_only_costs(
        self, project_id: int, run_id: int | None = None
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

        actual_paid = 0.0
        openai_sim = 0.0
        anthropic_sim = 0.0
        google_sim = 0.0

        for call in calls:
            input_tokens = call.input_tokens
            output_tokens = call.output_tokens

            # Map tier
            is_chief = (
                call.provider in {"openrouter", "nvidia", "omniroute"}
                or "chief" in call.reason.lower()
                or "contract" in call.reason.lower()
                or "repair" in call.reason.lower()
                or "review" in call.reason.lower()
            )
            is_small = (
                "pr" in call.reason.lower()
                or "summary" in call.reason.lower()
                or "changelog" in call.reason.lower()
            )
            tier = "large" if is_chief else ("small" if is_small else "medium")

            # OpenAI Simulation
            op_in, op_out = snapshot_prices(snapshots, BASELINE_MODELS["OpenAI"][tier])
            openai_sim += (input_tokens * op_in + output_tokens * op_out) / 1_000_000

            # Anthropic Simulation
            ant_in, ant_out = snapshot_prices(snapshots, BASELINE_MODELS["Anthropic"][tier])
            anthropic_sim += (input_tokens * ant_in + output_tokens * ant_out) / 1_000_000

            # Google Simulation
            gg_in, gg_out = snapshot_prices(snapshots, BASELINE_MODELS["Google"][tier])
            google_sim += (input_tokens * gg_in + output_tokens * gg_out) / 1_000_000

            if is_billed_call(call.provider, call.estimated_cost_usd):
                if call.estimated_cost_usd <= 0:
                    raise RuntimeError(
                        f"Paid model call {call.id or 'unknown'} has unknown cost; "
                        "simulation cannot treat it as zero."
                    )
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
