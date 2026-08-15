from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.services.pricing import (
    DEFAULT_MAX_GATEWAY_CALLS,
    is_free_gateway_model,
    is_gateway_provider,
    is_paid_provider,
)
from localforge.storage.orm import ModelCallLedgerORM, ModelPricingSnapshotORM, RunORM

OPENROUTER_MINIMAX_M3_INPUT_PER_MILLION = 0.30
OPENROUTER_MINIMAX_M3_OUTPUT_PER_MILLION = 1.20


def estimate_paid_call_cost_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    input_per_million: float = OPENROUTER_MINIMAX_M3_INPUT_PER_MILLION,
    output_per_million: float = OPENROUTER_MINIMAX_M3_OUTPUT_PER_MILLION,
) -> float:
    return (max(input_tokens, 0) / 1_000_000) * input_per_million + (
        max(output_tokens, 0) / 1_000_000
    ) * output_per_million


class ModelCallLedgerService:
    # Class-level buffer to preserve calls across transaction rollbacks
    _pending_calls: list[domain.ModelCallLedger] = []

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_call(self, call: domain.ModelCallLedger) -> domain.ModelCallLedger:
        if is_paid_provider(call.provider):
            result = await self.session.execute(
                select(ModelPricingSnapshotORM).where(
                    ModelPricingSnapshotORM.model_name == call.model
                )
            )
            snapshot = result.scalar_one_or_none()
            if snapshot is None:
                metadata = dict(call.metadata or {})
                try:
                    input_price = float(metadata["pricing_input_per_million"])
                    output_price = float(metadata["pricing_output_per_million"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Missing persisted or provider-catalog pricing for paid model {call.model!r}."
                    ) from exc
                if input_price < 0 or output_price < 0:
                    raise ValueError(f"Provider-catalog pricing is invalid for paid model {call.model!r}.")
                observed_cost = (
                    max(call.input_tokens, 0) * input_price
                    + max(call.output_tokens, 0) * output_price
                ) / 1_000_000
                metadata["pricing_measurement_source"] = "PROVIDER_CATALOG"
            else:
                observed_cost = (
                    max(call.input_tokens, 0) * float(snapshot.input_price_per_million)
                    + max(call.output_tokens, 0) * float(snapshot.output_price_per_million)
                ) / 1_000_000
                metadata = dict(call.metadata or {})
                metadata["pricing_snapshot_id"] = snapshot.id
                metadata["pricing_measurement_source"] = "MODEL_PRICING_SNAPSHOT"
            call = call.model_copy(
                update={"estimated_cost_usd": observed_cost, "metadata": metadata}
            )
        elif is_gateway_provider(call.provider):
            metadata = dict(call.metadata or {})
            if is_free_gateway_model(call.model):
                metadata["pricing_measurement_source"] = "NON_BILLED_GATEWAY_ROUTE"
                call = call.model_copy(
                    update={"estimated_cost_usd": 0.0, "metadata": metadata}
                )
            else:
                metadata["pricing_measurement_source"] = (
                    "GATEWAY_REPORTED_COST"
                    if call.estimated_cost_usd > 0.0
                    else "NON_BILLED_GATEWAY_ROUTE"
                )
                call = call.model_copy(update={"metadata": metadata})
        else:
            metadata = dict(call.metadata or {})
            metadata["pricing_measurement_source"] = "NON_BILLED_PROVIDER"
            call = call.model_copy(
                update={"estimated_cost_usd": 0.0, "metadata": metadata}
            )
        orm_obj = ModelCallLedgerORM.from_domain(call)
        self.session.add(orm_obj)
        await self.session.flush()
        self._pending_calls.append(call)
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
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        if provider is not None and not (
            is_paid_provider(provider) or is_gateway_provider(provider)
        ):
            return
        if run_id is None:
            return
        run = await self.session.get(RunORM, run_id)
        if run is None:
            return
        limits = run.resource_limits or {}
        totals = await self._run_totals(project_id=project_id, run_id=run_id)
        gateway_call = is_gateway_provider(provider or "")
        if gateway_call:
            gateway_limit = limits.get("max_gateway_calls", DEFAULT_MAX_GATEWAY_CALLS)
            gateway_calls = totals["gateway_calls"] + 1
            if gateway_limit is not None and gateway_calls > gateway_limit:
                raise ValueError(
                    "Chief Engineer gateway budget exceeded: "
                    f"max_gateway_calls={gateway_limit}, requested={gateway_calls}"
                )
            # The gateway is the billing authority. Before a call it may not
            # expose a usable price, so do not invent a paid estimate. Any
            # non-zero gateway cost already persisted in the ledger remains
            # part of the USD checks below and can block the next call.
            checks = [
                ("max_paid_usd", totals["estimated_cost_usd"]),
                ("max_paid_usd_absolute", totals["estimated_cost_usd"]),
            ]
        else:
            estimated_cost = estimate_paid_call_cost_usd(
                estimated_input_tokens, estimated_output_tokens
            )
            checks = [
                ("max_paid_calls", totals["paid_calls"] + 1),
                (
                    "max_paid_input_tokens",
                    totals["paid_input_tokens"] + estimated_input_tokens,
                ),
                (
                    "max_paid_output_tokens",
                    totals["paid_output_tokens"] + estimated_output_tokens,
                ),
                ("max_paid_usd", totals["estimated_cost_usd"] + estimated_cost),
                (
                    "max_paid_usd_absolute",
                    totals["estimated_cost_usd"] + estimated_cost,
                ),
            ]
        for key, value in checks:
            limit = limits.get(key)
            if limit is not None and value > limit:
                raise ValueError(
                    f"Chief Engineer {'gateway' if gateway_call else 'paid'} budget exceeded: "
                    f"{key}={limit}, requested={value}"
                )

    async def get_run_totals(self, *, project_id: int, run_id: int) -> dict[str, float]:
        return await self._run_totals(project_id=project_id, run_id=run_id)

    async def _run_totals(self, *, project_id: int, run_id: int) -> dict[str, float]:
        result = await self.session.execute(
            select(
                ModelCallLedgerORM.provider,
                ModelCallLedgerORM.input_tokens,
                ModelCallLedgerORM.output_tokens,
                ModelCallLedgerORM.estimated_cost_usd,
            ).where(
                ModelCallLedgerORM.project_id == project_id,
                ModelCallLedgerORM.run_id == run_id,
            )
        )
        calls = 0
        input_tokens = 0
        output_tokens = 0
        estimated_cost_usd = 0.0
        gateway_calls = 0
        paid_calls = 0
        paid_input_tokens = 0
        paid_output_tokens = 0
        for provider, call_input, call_output, call_cost in result.all():
            calls += 1
            input_tokens += int(call_input or 0)
            output_tokens += int(call_output or 0)
            estimated_cost_usd += float(call_cost or 0.0)
            if is_gateway_provider(provider):
                gateway_calls += 1
            elif is_paid_provider(provider):
                paid_calls += 1
                paid_input_tokens += int(call_input or 0)
                paid_output_tokens += int(call_output or 0)
        return {
            "calls": float(calls),
            "input_tokens": float(input_tokens),
            "output_tokens": float(output_tokens),
            "estimated_cost_usd": float(estimated_cost_usd),
            "gateway_calls": float(gateway_calls),
            "paid_calls": float(paid_calls),
            "paid_input_tokens": float(paid_input_tokens),
            "paid_output_tokens": float(paid_output_tokens),
        }

    async def list_pricing_sources(self) -> list[domain.PricingSource]:
        from localforge.storage.orm import PricingSourceORM

        result = await self.session.execute(
            select(PricingSourceORM).order_by(PricingSourceORM.provider)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def list_pricing_snapshots(self) -> list[domain.ModelPricingSnapshot]:
        from localforge.storage.orm import ModelPricingSnapshotORM

        result = await self.session.execute(
            select(ModelPricingSnapshotORM).order_by(ModelPricingSnapshotORM.model_name)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_pricing_snapshot(
        self,
        pricing_source_id: int,
        model_name: str,
        input_price_per_million: float,
        output_price_per_million: float,
        cached_input_price_per_million: float = 0.0,
    ) -> domain.ModelPricingSnapshot:
        from localforge.storage.orm import ModelPricingSnapshotORM

        result = await self.session.execute(
            select(ModelPricingSnapshotORM).where(ModelPricingSnapshotORM.model_name == model_name)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.pricing_source_id = pricing_source_id
            existing.input_price_per_million = input_price_per_million
            existing.output_price_per_million = output_price_per_million
            existing.cached_input_price_per_million = cached_input_price_per_million
            await self.session.flush()
            return existing.to_domain()
        else:
            new_snap = ModelPricingSnapshotORM(
                pricing_source_id=pricing_source_id,
                model_name=model_name,
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
                cached_input_price_per_million=cached_input_price_per_million,
                is_manual=True,
            )
            self.session.add(new_snap)
            await self.session.flush()
            return new_snap.to_domain()

    async def create_pricing_source(self, source: domain.PricingSource) -> domain.PricingSource:
        from localforge.storage.orm import PricingSourceORM

        orm_obj = PricingSourceORM.from_domain(source)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()
