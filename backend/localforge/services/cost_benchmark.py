from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from localforge.models import domain
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

        actual_paid_usd = 0.0
        actual_calls = 0
        local_calls_avoided = 0

        openai_hypothetical = 0.0
        anthropic_hypothetical = 0.0
        google_hypothetical = 0.0

        for call in calls:
            input_tokens = call.input_tokens
            output_tokens = call.output_tokens

            is_chief = call.provider == "openrouter" or "chief" in call.reason.lower() or "contract" in call.reason.lower() or "repair" in call.reason.lower() or "review" in call.reason.lower()
            is_small = "pr" in call.reason.lower() or "summary" in call.reason.lower() or "changelog" in call.reason.lower()
            tier = "large" if is_chief else ("small" if is_small else "medium")

            # OpenAI
            op_in, op_out = get_prices(provider_map["OpenAI"][tier])
            openai_hypothetical += (input_tokens * op_in + output_tokens * op_out) / 1_000_000

            # Anthropic
            ant_in, ant_out = get_prices(provider_map["Anthropic"][tier])
            anthropic_hypothetical += (input_tokens * ant_in + output_tokens * ant_out) / 1_000_000

            # Google
            gg_in, gg_out = get_prices(provider_map["Google"][tier])
            google_hypothetical += (input_tokens * gg_in + output_tokens * gg_out) / 1_000_000

            if call.provider == "openrouter":
                actual_paid_usd += call.estimated_cost_usd
                actual_calls += 1
            else:
                local_calls_avoided += 1

        return {
            "actual_paid_usd": actual_paid_usd,
            "actual_calls": actual_calls,
            "local_calls_avoided": local_calls_avoided,
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

        md = f"""# LocalForge OS — Cost Benchmark Report

Comparing hybrid execution (API + Local) against hypothetical API-only competitor baselines.

| Metric | LocalForge Actual | OpenAI API-Only | Anthropic API-Only | Google API-Only |
| :--- | :---: | :---: | :---: | :---: |
| **Total Spend (USD)** | ${metrics['actual_paid_usd']:.4f} | ${metrics['openai_hypothetical_usd']:.4f} | ${metrics['anthropic_hypothetical_usd']:.4f} | ${metrics['google_hypothetical_usd']:.4f} |
| **Actual Paid Calls** | {metrics['actual_calls']} | - | - | - |
| **Local Calls Avoided** | {metrics['local_calls_avoided']} | - | - | - |
| **Projected Savings** | - | ${metrics['openai_savings_usd']:.4f} | ${metrics['anthropic_savings_usd']:.4f} | ${metrics['google_savings_usd']:.4f} |

*Note: Baselines are estimated token-cost comparison models based on official pricing snapshots, not exact proprietary billing invoices.*

*Pricing snapshots references used: {snapshot_ids}*
"""
        return md
