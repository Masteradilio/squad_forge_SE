import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import RunnerHealthState, RunnerLane
from localforge.storage.orm import RunnerDispatchLogORM, RunnerPoolStateORM

logger = logging.getLogger(__name__)


class RunnerPoolService:
    """Service layer for Capability-Aware RunnerPool management, health tracking, deterministic dispatch, and backpressure."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def register_runner(
        self,
        runner_id: str,
        name: str,
        lane: RunnerLane = RunnerLane.INLINE,
        capabilities: domain.RunnerCapability | None = None,
        max_concurrency: int = 4,
    ) -> domain.RunnerPoolState:
        """Register or update a runner in the pool."""
        stmt = select(RunnerPoolStateORM).where(RunnerPoolStateORM.runner_id == runner_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()

        caps = capabilities or domain.RunnerCapability(lane=lane, max_concurrency=max_concurrency)

        if orm_obj:
            orm_obj.name = name
            orm_obj.lane = lane.value
            orm_obj.max_concurrency = max_concurrency
            orm_obj.capabilities_json = caps.model_dump(mode="json")
        else:
            state_domain = domain.RunnerPoolState(
                runner_id=runner_id,
                name=name,
                lane=lane,
                health_state=RunnerHealthState.READY,
                max_concurrency=max_concurrency,
                capabilities=caps,
            )
            orm_obj = RunnerPoolStateORM.from_domain(state_domain)
            self.session.add(orm_obj)

        await self.session.flush()
        return orm_obj.to_domain()

    async def update_runner_health(
        self, runner_id: str, health_state: RunnerHealthState, quarantine_reason: str | None = None
    ) -> domain.RunnerPoolState:
        """Update the health state of a runner (e.g. READY, DEGRADED, QUARANTINED)."""
        stmt = select(RunnerPoolStateORM).where(RunnerPoolStateORM.runner_id == runner_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Runner with ID '{runner_id}' not found.")

        orm_obj.health_state = health_state.value
        orm_obj.quarantine_reason = quarantine_reason
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_runners(self) -> list[domain.RunnerPoolState]:
        """List all registered runners and their current states."""
        stmt = select(RunnerPoolStateORM)
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def dispatch_task(
        self,
        project_id: int,
        task_run_id: int,
        required_lane: RunnerLane | None = None,
        required_tools: list[str] | None = None,
        required_task_type: str | None = None,
    ) -> tuple[domain.RunnerPoolState | None, str, domain.RunnerDispatchLog]:
        """Perform deterministic, capability-aware dispatch for a task run.

        Returns:
            (selected_runner: RunnerPoolState | None, dispatch_status: str, dispatch_log: RunnerDispatchLog)
        """
        all_runners = await self.list_runners()
        rejection_reasons: dict[str, str] = {}
        ranking_scores: dict[str, float] = {}
        eligible_runners: list[tuple[domain.RunnerPoolState, float]] = []

        req_tools = set(required_tools or [])

        # Filter & Rank
        for runner in all_runners:
            # Hard filter 1: Health State
            if runner.health_state in (RunnerHealthState.QUARANTINED, RunnerHealthState.UNAVAILABLE):
                rejection_reasons[runner.runner_id] = f"Excluded due to health state '{runner.health_state.value}'."
                continue

            # Hard filter 2: Lane
            if required_lane and runner.lane != required_lane:
                rejection_reasons[runner.runner_id] = f"Lane mismatch: expected '{required_lane.value}', got '{runner.lane.value}'."
                continue

            # Hard filter 3: Tools
            missing_tools = req_tools - set(runner.capabilities.tools)
            if missing_tools:
                rejection_reasons[runner.runner_id] = f"Missing required tools: {sorted(list(missing_tools))}."
                continue

            # Hard filter 4: Supported Task Types
            if required_task_type and runner.capabilities.supported_task_types:
                if required_task_type not in runner.capabilities.supported_task_types:
                    rejection_reasons[runner.runner_id] = f"Task type '{required_task_type}' not supported."
                    continue

            # Hard filter 5: Concurrency Capacity
            if runner.active_tasks_count >= runner.max_concurrency:
                rejection_reasons[runner.runner_id] = f"Concurrency capacity exhausted ({runner.active_tasks_count}/{runner.max_concurrency})."
                continue

            # Score formula: (success_rate * 100) - (active_tasks * 10) + health_bonus
            health_bonus = 50.0 if runner.health_state == RunnerHealthState.READY else 20.0
            score = (runner.success_rate * 100.0) - (runner.active_tasks_count * 10.0) + health_bonus
            ranking_scores[runner.runner_id] = score
            eligible_runners.append((runner, score))

        if not eligible_runners:
            dispatch_status = "NO_COMPATIBLE_RUNNER"
            log_domain = domain.RunnerDispatchLog(
                project_id=project_id,
                task_run_id=task_run_id,
                selected_runner_id=None,
                dispatch_status=dispatch_status,
                ranking_scores_json=ranking_scores,
                rejection_reasons_json=rejection_reasons,
            )
            orm_log = RunnerDispatchLogORM.from_domain(log_domain)
            self.session.add(orm_log)
            await self.session.flush()
            return None, dispatch_status, orm_log.to_domain()

        # Stable tie-breaking: highest score first, then runner_id alphabetically
        eligible_runners.sort(key=lambda item: (-item[1], item[0].runner_id))
        winning_runner, _ = eligible_runners[0]

        # Record runner capacity reservation
        stmt = select(RunnerPoolStateORM).where(RunnerPoolStateORM.runner_id == winning_runner.runner_id)
        res = await self.session.execute(stmt)
        orm_runner = res.scalar_one()
        orm_runner.active_tasks_count += 1
        if orm_runner.active_tasks_count >= orm_runner.max_concurrency:
            orm_runner.health_state = RunnerHealthState.BUSY.value

        dispatch_status = "SUCCESS"
        log_domain = domain.RunnerDispatchLog(
            project_id=project_id,
            task_run_id=task_run_id,
            selected_runner_id=winning_runner.runner_id,
            dispatch_status=dispatch_status,
            ranking_scores_json=ranking_scores,
            rejection_reasons_json=rejection_reasons,
        )
        orm_log = RunnerDispatchLogORM.from_domain(log_domain)
        self.session.add(orm_log)
        await self.session.flush()

        return orm_runner.to_domain(), dispatch_status, orm_log.to_domain()

    async def release_runner_lease(self, runner_id: str, success: bool = True) -> domain.RunnerPoolState:
        """Release concurrency lease and update historical outcome metrics."""
        stmt = select(RunnerPoolStateORM).where(RunnerPoolStateORM.runner_id == runner_id)
        res = await self.session.execute(stmt)
        orm_runner = res.scalar_one_or_none()
        if not orm_runner:
            raise ValueError(f"Runner '{runner_id}' not found.")

        if orm_runner.active_tasks_count > 0:
            orm_runner.active_tasks_count -= 1

        # Restore READY health if it was BUSY
        if orm_runner.health_state == RunnerHealthState.BUSY.value and orm_runner.active_tasks_count < orm_runner.max_concurrency:
            orm_runner.health_state = RunnerHealthState.READY.value

        # Update success rate (moving average)
        factor = 1.0 if success else 0.0
        orm_runner.success_rate = round((orm_runner.success_rate * 0.8) + (factor * 0.2), 3)

        await self.session.flush()
        return orm_runner.to_domain()

    async def reconcile_leaked_leases(self) -> int:
        """Reconcile leaked leases after daemon restart by resetting active task counts."""
        stmt = select(RunnerPoolStateORM).where(RunnerPoolStateORM.active_tasks_count > 0)
        res = await self.session.execute(stmt)
        runners = res.scalars().all()
        count = 0
        for r in runners:
            r.active_tasks_count = 0
            if r.health_state == RunnerHealthState.BUSY.value:
                r.health_state = RunnerHealthState.READY.value
            count += 1

        await self.session.flush()
        return count
