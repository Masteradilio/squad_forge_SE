from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.storage.orm import ModelCallLedgerORM, RunORM


OPENROUTER_MINIMAX_M3_INPUT_PER_MILLION = 0.30
OPENROUTER_MINIMAX_M3_OUTPUT_PER_MILLION = 1.20


def estimate_paid_call_cost_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    input_per_million: float = OPENROUTER_MINIMAX_M3_INPUT_PER_MILLION,
    output_per_million: float = OPENROUTER_MINIMAX_M3_OUTPUT_PER_MILLION,
) -> float:
    return (
        (max(input_tokens, 0) / 1_000_000) * input_per_million
        + (max(output_tokens, 0) / 1_000_000) * output_per_million
    )


class ModelCallLedgerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_call(self, call: domain.ModelCallLedger) -> domain.ModelCallLedger:
        orm_obj = ModelCallLedgerORM.from_domain(call)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_calls(
        self, *, project_id: int, run_id: int | None = None
    ) -> list[domain.ModelCallLedger]:
        stmt = (
            select(ModelCallLedgerORM)
            .where(ModelCallLedgerORM.project_id == project_id)
            .order_by(ModelCallLedgerORM.created_at.asc(), ModelCallLedgerORM.id.asc())
        )
        if run_id is not None:
            stmt = stmt.where(ModelCallLedgerORM.run_id == run_id)
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def ensure_budget(
        self,
        *,
        project_id: int,
        run_id: int | None,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> None:
        if run_id is None:
            return
        run = await self.session.get(RunORM, run_id)
        if run is None:
            return
        limits = run.resource_limits or {}
        totals = await self._run_totals(project_id=project_id, run_id=run_id)
        estimated_cost = estimate_paid_call_cost_usd(
            estimated_input_tokens, estimated_output_tokens
        )
        checks = [
            ("max_paid_calls", totals["calls"] + 1),
            ("max_paid_input_tokens", totals["input_tokens"] + estimated_input_tokens),
            ("max_paid_output_tokens", totals["output_tokens"] + estimated_output_tokens),
            ("max_paid_usd", totals["estimated_cost_usd"] + estimated_cost),
        ]
        for key, value in checks:
            limit = limits.get(key)
            if limit is not None and value > limit:
                raise ValueError(
                    f"Chief Engineer paid budget exceeded: {key}={limit}, requested={value}"
                )

    async def _run_totals(self, *, project_id: int, run_id: int) -> dict[str, float]:
        result = await self.session.execute(
            select(
                func.count(ModelCallLedgerORM.id),
                func.coalesce(func.sum(ModelCallLedgerORM.input_tokens), 0),
                func.coalesce(func.sum(ModelCallLedgerORM.output_tokens), 0),
                func.coalesce(func.sum(ModelCallLedgerORM.estimated_cost_usd), 0.0),
            ).where(
                ModelCallLedgerORM.project_id == project_id,
                ModelCallLedgerORM.run_id == run_id,
            )
        )
        calls, input_tokens, output_tokens, estimated_cost_usd = result.one()
        return {
            "calls": float(calls),
            "input_tokens": float(input_tokens),
            "output_tokens": float(output_tokens),
            "estimated_cost_usd": float(estimated_cost_usd),
        }
