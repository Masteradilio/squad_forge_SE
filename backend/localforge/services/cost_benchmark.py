from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.services.pricing import BASELINE_MODELS, is_billed_call, is_gateway_provider, snapshot_prices
from localforge.storage.orm import ModelCallLedgerORM, ModelPricingSnapshotORM


class CostBenchmarkService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def calculate_benchmarks(self, project_id: int, run_id: int | None = None) -> dict[str, float]:
        stmt = select(ModelCallLedgerORM).where(ModelCallLedgerORM.project_id == project_id)
        if run_id is not None:
            stmt = stmt.where(ModelCallLedgerORM.run_id == run_id)

        res = await self.session.execute(stmt)
        calls = res.scalars().all()

        # 1. Fetch pricing snapshots from DB
        snap_res = await self.session.execute(select(ModelPricingSnapshotORM))
        snapshots = {s.model_name: s for s in snap_res.scalars().all()}

        actual_paid_usd = 0.0
        actual_calls = 0
        local_calls_avoided = 0
        gateway_calls = 0
        free_gateway_calls = 0

        openai_hypothetical = 0.0
        anthropic_hypothetical = 0.0
        google_hypothetical = 0.0

        for call in calls:
            input_tokens = call.input_tokens
            output_tokens = call.output_tokens

            is_chief = (
                call.provider in {"openrouter", "nvidia", "omniroute"}
                or "chief" in call.reason.lower()
                or "contract" in call.reason.lower()
                or "repair" in call.reason.lower()
                or "review" in call.reason.lower()
            )
            is_small = "pr" in call.reason.lower() or "summary" in call.reason.lower() or "changelog" in call.reason.lower()
            tier = "large" if is_chief else ("small" if is_small else "medium")

            # OpenAI
            op_in, op_out = snapshot_prices(snapshots, BASELINE_MODELS["OpenAI"][tier])
            openai_hypothetical += (input_tokens * op_in + output_tokens * op_out) / 1_000_000

            # Anthropic
            ant_in, ant_out = snapshot_prices(snapshots, BASELINE_MODELS["Anthropic"][tier])
            anthropic_hypothetical += (input_tokens * ant_in + output_tokens * ant_out) / 1_000_000

            # Google
            gg_in, gg_out = snapshot_prices(snapshots, BASELINE_MODELS["Google"][tier])
            google_hypothetical += (input_tokens * gg_in + output_tokens * gg_out) / 1_000_000

            if is_gateway_provider(call.provider):
                gateway_calls += 1
            if is_billed_call(call.provider, call.estimated_cost_usd):
                if call.estimated_cost_usd <= 0:
                    raise RuntimeError(
                        f"Paid model call {call.id or 'unknown'} has unknown cost; "
                        "cost reports cannot treat it as zero."
                    )
                actual_paid_usd += call.estimated_cost_usd
                actual_calls += 1
            elif is_gateway_provider(call.provider):
                free_gateway_calls += 1
            else:
                local_calls_avoided += 1

        return {
            "actual_paid_usd": actual_paid_usd,
            "actual_calls": actual_calls,
            "local_calls_avoided": local_calls_avoided,
            "gateway_calls": gateway_calls,
            "free_gateway_calls": free_gateway_calls,
            "openai_hypothetical_usd": openai_hypothetical,
            "anthropic_hypothetical_usd": anthropic_hypothetical,
            "google_hypothetical_usd": google_hypothetical,
            "openai_savings_usd": max(0.0, openai_hypothetical - actual_paid_usd),
            "anthropic_savings_usd": max(0.0, anthropic_hypothetical - actual_paid_usd),
            "google_savings_usd": max(0.0, google_hypothetical - actual_paid_usd),
        }

    async def generate_markdown_report(self, project_id: int, run_id: int | None = None) -> str:
        metrics = await self.calculate_benchmarks(project_id, run_id)

        # Buscar snapshots ativos no banco
        snap_res = await self.session.execute(select(ModelPricingSnapshotORM))
        snapshots = snap_res.scalars().all()
        snapshot_ids = ", ".join([f"#{s.id} ({s.model_name})" for s in snapshots])
        spend_row = (
            f"| **Total Spend (USD)** | ${metrics['actual_paid_usd']:.4f} | "
            f"${metrics['openai_hypothetical_usd']:.4f} | "
            f"${metrics['anthropic_hypothetical_usd']:.4f} | "
            f"${metrics['google_hypothetical_usd']:.4f} |"
        )
        savings_row = (
            f"| **Projected Savings** | - | ${metrics['openai_savings_usd']:.4f} | "
            f"${metrics['anthropic_savings_usd']:.4f} | "
            f"${metrics['google_savings_usd']:.4f} |"
        )

        md = f"""# LocalForge OS — Cost Benchmark Report

Comparing hybrid execution (API + Local) against hypothetical API-only competitor baselines.

| Metric | LocalForge Actual | OpenAI API-Only | Anthropic API-Only | Google API-Only |
| :--- | :---: | :---: | :---: | :---: |
{spend_row}
| **Actual Paid Calls** | {metrics["actual_calls"]} | - | - | - |
| **OmniRoute Gateway Calls** | {metrics["gateway_calls"]} | - | - | - |
| **Free Gateway Calls** | {metrics["free_gateway_calls"]} | - | - | - |
| **Local Calls Avoided** | {metrics["local_calls_avoided"]} | - | - | - |
{savings_row}

*Note: Baselines are estimated token-cost comparison models based on official pricing
snapshots, not exact proprietary billing invoices.*

*Pricing snapshots references used: {snapshot_ids}*
"""
        return md
