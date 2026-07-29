import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import RunnerHealthState, RunnerLane, TaskRunStatus
from localforge.storage.orm import RunnerDispatchLogORM, RunnerPoolStateORM, TaskRunORM

logger = logging.getLogger(__name__)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RunnerPoolService:
    """Capability-aware RunnerPool management, health tracking, and dispatch."""

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

    async def list_dispatch_logs_for_task_run(
        self, task_run_id: int
    ) -> list[domain.RunnerDispatchLog]:
        """List persisted dispatch decisions for a task run."""
        stmt = select(RunnerDispatchLogORM).where(RunnerDispatchLogORM.task_run_id == task_run_id)
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def dispatch_task(
        self,
        project_id: int,
        task_run_id: int,
        required_lane: RunnerLane | None = None,
        required_tools: list[str] | None = None,
        required_task_type: str | None = None,
        lease_ttl_seconds: int = 3600,
        backpressure_queue_limit: int = 100,
    ) -> tuple[domain.RunnerPoolState | None, str, domain.RunnerDispatchLog]:
        """Perform deterministic, capability-aware dispatch for a task run.

        Returns:
            Selected runner, dispatch status, and persisted dispatch log.
        """
        all_runners = await self.list_runners()
        rejection_reasons: dict[str, str] = {}
        ranking_scores: dict[str, float] = {}
        eligible_runners: list[tuple[domain.RunnerPoolState, float]] = []
        capacity_blocked_runners: list[str] = []

        req_tools = set(required_tools or [])

        # Filter & Rank
        for runner in all_runners:
            # Hard filter 1: Health State
            if runner.health_state in (
                RunnerHealthState.QUARANTINED,
                RunnerHealthState.UNAVAILABLE,
            ):
                rejection_reasons[runner.runner_id] = (
                    f"Excluded due to health state '{runner.health_state.value}'."
                )
                continue

            # Hard filter 2: Lane
            if required_lane and runner.lane != required_lane:
                rejection_reasons[runner.runner_id] = (
                    f"Lane mismatch: expected '{required_lane.value}', got '{runner.lane.value}'."
                )
                continue

            # Hard filter 3: Tools
            missing_tools = req_tools - set(runner.capabilities.tools)
            if missing_tools:
                rejection_reasons[runner.runner_id] = (
                    f"Missing required tools: {sorted(list(missing_tools))}."
                )
                continue

            # Hard filter 4: Supported Task Types
            if required_task_type and runner.capabilities.supported_task_types:
                if required_task_type not in runner.capabilities.supported_task_types:
                    rejection_reasons[runner.runner_id] = (
                        f"Task type '{required_task_type}' not supported."
                    )
                    continue

            # Hard filter 5: Concurrency Capacity
            if runner.active_tasks_count >= runner.max_concurrency:
                capacity_blocked_runners.append(runner.runner_id)
                rejection_reasons[runner.runner_id] = (
                    "Concurrency capacity exhausted "
                    f"({runner.active_tasks_count}/{runner.max_concurrency})."
                )
                continue

            # Score formula: (success_rate * 100) - (active_tasks * 10) + health_bonus
            health_bonus = 50.0 if runner.health_state == RunnerHealthState.READY else 20.0
            score = (
                (runner.success_rate * 100.0) - (runner.active_tasks_count * 10.0) + health_bonus
            )
            ranking_scores[runner.runner_id] = score
            eligible_runners.append((runner, score))

        if not eligible_runners:
            dispatch_status = "NO_COMPATIBLE_RUNNER"
            if capacity_blocked_runners:
                queue_depth = await self._backpressure_queue_depth(project_id)
                if queue_depth >= backpressure_queue_limit:
                    dispatch_status = "BACKPRESSURE_QUEUE_FULL"
                    rejection_reasons["_backpressure"] = (
                        f"Backpressure queue limit reached ({queue_depth}/{backpressure_queue_limit})."
                    )
                else:
                    dispatch_status = "BACKPRESSURE_LIMITED"
                    rejection_reasons["_backpressure"] = (
                        "Compatible runners are saturated; retry after capacity is released. "
                        f"queue_position={queue_depth + 1}; "
                        f"queue_limit={backpressure_queue_limit}; "
                        f"blocked_runners={','.join(sorted(capacity_blocked_runners))}"
                    )
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

        # Reserve capacity atomically so concurrent schedulers cannot over-allocate.
        reserve_stmt = (
            update(RunnerPoolStateORM)
            .where(
                RunnerPoolStateORM.runner_id == winning_runner.runner_id,
                RunnerPoolStateORM.active_tasks_count < RunnerPoolStateORM.max_concurrency,
            )
            .values(active_tasks_count=RunnerPoolStateORM.active_tasks_count + 1)
        )
        reserve_result = await self.session.execute(reserve_stmt)
        if getattr(reserve_result, "rowcount", 0) != 1:
            rejection_reasons[winning_runner.runner_id] = (
                "Concurrency capacity changed before reservation completed."
            )
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

        stmt = select(RunnerPoolStateORM).where(
            RunnerPoolStateORM.runner_id == winning_runner.runner_id
        )
        res = await self.session.execute(stmt)
        orm_runner = res.scalar_one()
        if orm_runner.active_tasks_count >= orm_runner.max_concurrency:
            orm_runner.health_state = RunnerHealthState.BUSY.value

        dispatch_status = "SUCCESS"
        now = datetime.now(UTC)
        lease_token = str(uuid4())
        log_domain = domain.RunnerDispatchLog(
            project_id=project_id,
            task_run_id=task_run_id,
            selected_runner_id=winning_runner.runner_id,
            lease_token=lease_token,
            lease_owner_id=winning_runner.runner_id,
            lease_expires_at=now + timedelta(seconds=lease_ttl_seconds),
            heartbeat_at=now,
            dispatch_status=dispatch_status,
            ranking_scores_json=ranking_scores,
            rejection_reasons_json=rejection_reasons,
        )
        orm_log = RunnerDispatchLogORM.from_domain(log_domain)
        self.session.add(orm_log)
        await self.session.flush()

        return orm_runner.to_domain(), dispatch_status, orm_log.to_domain()

    async def _backpressure_queue_depth(self, project_id: int) -> int:
        stmt = select(func.count(RunnerDispatchLogORM.id)).where(
            RunnerDispatchLogORM.project_id == project_id,
            RunnerDispatchLogORM.dispatch_status == "BACKPRESSURE_LIMITED",
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def release_runner_lease(
        self,
        runner_id: str,
        success: bool = True,
        *,
        task_run_id: int | None = None,
        lease_token: str | None = None,
    ) -> domain.RunnerPoolState:
        """Release concurrency lease and update historical outcome metrics."""
        stmt = select(RunnerPoolStateORM).where(RunnerPoolStateORM.runner_id == runner_id)
        res = await self.session.execute(stmt)
        orm_runner = res.scalar_one_or_none()
        if not orm_runner:
            raise ValueError(f"Runner '{runner_id}' not found.")

        if lease_token is not None:
            if task_run_id is None:
                raise ValueError("task_run_id is required when releasing by lease token.")
            log_stmt = (
                select(RunnerDispatchLogORM)
                .where(
                    RunnerDispatchLogORM.task_run_id == task_run_id,
                    RunnerDispatchLogORM.selected_runner_id == runner_id,
                    RunnerDispatchLogORM.dispatch_status == "SUCCESS",
                )
                .order_by(RunnerDispatchLogORM.created_at.desc())
            )
            log_result = await self.session.execute(log_stmt)
            lease_log = log_result.scalars().first()
            now = datetime.now(UTC)
            if lease_log is None or lease_log.lease_token != lease_token:
                raise ValueError("Runner lease token does not match the active owner.")
            if (
                lease_log.lease_expires_at is not None
                and _as_aware_utc(lease_log.lease_expires_at) <= now
            ):
                raise ValueError("Runner lease token has expired.")

        if orm_runner.active_tasks_count > 0:
            orm_runner.active_tasks_count -= 1

        # Restore READY health if it was BUSY
        if (
            orm_runner.health_state == RunnerHealthState.BUSY.value
            and orm_runner.active_tasks_count < orm_runner.max_concurrency
        ):
            orm_runner.health_state = RunnerHealthState.READY.value

        # Update success rate (moving average)
        factor = 1.0 if success else 0.0
        orm_runner.success_rate = round((orm_runner.success_rate * 0.8) + (factor * 0.2), 3)

        await self.session.flush()
        return orm_runner.to_domain()

    async def cancel_runner_leases_for_task_run(self, task_run_id: int) -> int:
        """Cancel any active runner reservations for a task run.

        This is used by lifecycle kill/recovery paths where the original worker may no longer
        be alive to return its fenced lease token. Dispatch logs are marked terminal so repeated
        reconciliation calls do not decrement runner capacity more than once.
        """
        stmt = select(RunnerDispatchLogORM).where(
            RunnerDispatchLogORM.task_run_id == task_run_id,
            RunnerDispatchLogORM.dispatch_status == "SUCCESS",
            RunnerDispatchLogORM.selected_runner_id.is_not(None),
        )
        result = await self.session.execute(stmt)
        active_logs = result.scalars().all()
        if not active_logs:
            return 0

        released_count = 0
        for log in active_logs:
            if log.selected_runner_id is None:
                continue
            runner_stmt = select(RunnerPoolStateORM).where(
                RunnerPoolStateORM.runner_id == log.selected_runner_id
            )
            runner_result = await self.session.execute(runner_stmt)
            runner = runner_result.scalar_one_or_none()
            if runner is not None and runner.active_tasks_count > 0:
                runner.active_tasks_count -= 1
                if (
                    runner.health_state == RunnerHealthState.BUSY.value
                    and runner.active_tasks_count < runner.max_concurrency
                ):
                    runner.health_state = RunnerHealthState.READY.value
            log.dispatch_status = "CANCELLED"
            log.rejection_reasons_json = {
                **(log.rejection_reasons_json if isinstance(log.rejection_reasons_json, dict) else {}),
                "lifecycle": "Cancelled by loop lifecycle cascade.",
            }
            released_count += 1

        await self.session.flush()
        return released_count

    async def heartbeat_runner_lease(
        self,
        runner_id: str,
        *,
        task_run_id: int,
        lease_token: str,
        lease_ttl_seconds: int = 3600,
    ) -> domain.RunnerDispatchLog | None:
        """Refresh a runner dispatch lease only for the current fenced owner."""
        now = datetime.now(UTC)
        stmt = (
            select(RunnerDispatchLogORM)
            .where(
                RunnerDispatchLogORM.task_run_id == task_run_id,
                RunnerDispatchLogORM.selected_runner_id == runner_id,
                RunnerDispatchLogORM.lease_token == lease_token,
            )
            .order_by(RunnerDispatchLogORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        orm_log = result.scalars().first()
        if orm_log is None:
            return None
        orm_log.heartbeat_at = now
        orm_log.lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
        await self.session.flush()
        return orm_log.to_domain()

    async def reconcile_leaked_leases(self) -> int:
        """Reconcile runner capacity from persisted active task-run truth."""
        stmt = select(RunnerPoolStateORM)
        res = await self.session.execute(stmt)
        runners = res.scalars().all()
        count = 0
        active_statuses = {TaskRunStatus.PENDING.value, TaskRunStatus.RUNNING.value}
        for runner in runners:
            log_stmt = (
                select(RunnerDispatchLogORM)
                .join(TaskRunORM, TaskRunORM.id == RunnerDispatchLogORM.task_run_id)
                .where(
                    RunnerDispatchLogORM.selected_runner_id == runner.runner_id,
                    RunnerDispatchLogORM.dispatch_status == "SUCCESS",
                    TaskRunORM.status.in_(active_statuses),
                )
            )
            log_result = await self.session.execute(log_stmt)
            active_count = len(log_result.scalars().all())
            if runner.active_tasks_count != active_count:
                runner.active_tasks_count = active_count
                count += 1
            if runner.active_tasks_count >= runner.max_concurrency:
                runner.health_state = RunnerHealthState.BUSY.value
            elif runner.health_state == RunnerHealthState.BUSY.value:
                runner.health_state = RunnerHealthState.READY.value

        await self.session.flush()
        return count
