import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import (
    AuditEventActorType,
    AuditEventType,
    CircuitScope,
    LoopRunStatus,
    LoopRunVerdict,
    LoopStatus,
    RunMode,
    RunStatus,
    TaskStatus,
    TriggerKind,
)
from localforge.services.audit import AuditService
from localforge.services.circuit_breaker import CircuitBreakerService
from localforge.services.execution import ExecutionService
from localforge.services.external_events import validate_external_event_envelope, window_start
from localforge.services.loop_service import LoopService
from localforge.services.task import TaskService

logger = logging.getLogger(__name__)


class LoopCoordinator:
    """Coordinator engine managing durable loop state, cheap triage, restart recovery,

    and triggering scheduler runs for actionable items.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.loop_service = LoopService(session)
        self.execution_service = ExecutionService(session)
        self.audit_service = AuditService(session)
        self.circuit_breaker_service = CircuitBreakerService(session)
        self.task_service = TaskService(session)

    async def trigger_due_schedules(
        self, project_id: int, *, now: datetime | None = None, limit: int = 50
    ) -> list[domain.LoopRun]:
        """Claim and execute due interval/cron loop definitions once."""
        claimed = await self.loop_service.claim_due_schedules(project_id, now=now, limit=limit)
        runs: list[domain.LoopRun] = []
        for loop_def, idempotency_key in claimed:
            payload = loop_def.trigger.metadata.get("default_payload")
            if not isinstance(payload, dict):
                payload = None
            run = await self.trigger_loop(
                loop_id=loop_def.id or 0,
                trigger_kind=loop_def.trigger.kind,
                idempotency_key=idempotency_key,
                payload=payload,
            )
            runs.append(run)
        return runs

    async def trigger_loop(
        self,
        loop_id: int,
        trigger_kind: TriggerKind = TriggerKind.MANUAL,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
        triggered_at: datetime | None = None,
    ) -> domain.LoopRun:
        """Receive a trigger, enforce idempotency, run triage, and manage lifecycle."""
        if trigger_kind == TriggerKind.EVENT and not (
            payload and payload.get("_external_trigger_verified") is True
        ):
            raise ValueError("External event triggers must use the verified event adapter")

        loop_def = await self.loop_service.get_loop(loop_id)
        if not loop_def:
            raise ValueError(f"Loop definition with ID {loop_id} not found")

        if not loop_def.enabled or loop_def.status == LoopStatus.DISABLED:
            raise ValueError(f"Loop {loop_id} is disabled and cannot be executed")

        if loop_def.status == LoopStatus.PAUSED:
            raise ValueError(f"Loop {loop_id} is currently paused")

        # Check Circuit Breaker for this Loop
        (
            can_proceed,
            breaker_state,
            breaker_reason,
        ) = await self.circuit_breaker_service.check_breaker(
            project_id=loop_def.project_id,
            scope=CircuitScope.LOOP,
            target_id=str(loop_id),
        )
        if not can_proceed:
            raise ValueError(
                f"Loop {loop_id} is blocked by Circuit Breaker "
                f"({breaker_state.value}): {breaker_reason}"
            )

        current_time = triggered_at or datetime.now(UTC)
        key = idempotency_key or f"loop_{loop_id}_{trigger_kind}_{current_time.timestamp()}"

        # Deduplication check
        existing_run = await self.loop_service.get_loop_run_by_idempotency_key(key)
        if existing_run:
            logger.info(
                "Duplicate trigger received for loop %s with key %s. Returning existing run.",
                loop_id,
                key,
            )
            return existing_run

        # Create LoopRun record in PENDING state
        loop_run = domain.LoopRun(
            loop_id=loop_id,
            status=LoopRunStatus.TRIAGING,
            trigger_kind=trigger_kind,
            idempotency_key=key,
            triage_verdict=LoopRunVerdict.PENDING,
            started_at=current_time,
        )
        loop_run = await self.loop_service.create_loop_run(loop_run)

        # Audit trigger receipt
        await self._log_audit_event(
            project_id=loop_def.project_id,
            details=f"Loop {loop_id} triggered via {trigger_kind} (key: {key})",
        )

        # Run cheap triage
        if payload and "detector_error" in payload:
            error_message = str(payload["detector_error"])
            loop_run.status = LoopRunStatus.FAILED
            loop_run.triage_verdict = LoopRunVerdict.FAILED
            loop_run.error_message = f"Detector failed: {error_message}"
            loop_run.completed_at = datetime.now(UTC)
            loop_run = await self.loop_service.update_loop_run(loop_run)
            await self._log_audit_event(
                project_id=loop_def.project_id,
                details=f"Loop {loop_id} detector failed: {error_message[:500]}",
            )
            await self._update_loop_snapshot(loop_id, active_run_id=None)
            return loop_run

        is_actionable, items = await self._run_cheap_triage(loop_def, payload)

        if not is_actionable:
            # Triage verdict: NO_OP
            loop_run.status = LoopRunStatus.NO_OP
            loop_run.triage_verdict = LoopRunVerdict.NO_OP
            loop_run.completed_at = datetime.now(UTC)
            loop_run = await self.loop_service.update_loop_run(loop_run)

            await self._log_audit_event(
                project_id=loop_def.project_id,
                details=(
                    f"Loop {loop_id} run {loop_run.id} triaged as NO_OP. No scheduler run created."
                ),
            )

            # Update snapshot
            await self._update_loop_snapshot(loop_id, active_run_id=None)
            return loop_run

        # Triage verdict: ACTIONABLE -> Create scheduler Run
        loop_run.triage_verdict = LoopRunVerdict.ACTIONABLE
        loop_run.status = LoopRunStatus.RUNNING

        new_run = domain.Run(
            project_id=loop_def.project_id,
            mode=RunMode.UNATTENDED,
            status=RunStatus.PENDING,
            initiated_by="loop_coordinator",
        )

        scheduler_run = await self.execution_service.create_run(new_run)
        loop_run.scheduler_run_id = scheduler_run.id

        # Persist actionable items
        processed_count = 0
        for item_data in items:
            item_key = f"{key}_item_{item_data.get('external_id', processed_count)}"
            existing_item = await self.loop_service.get_loop_item_by_idempotency_key(item_key)
            if not existing_item:
                item = domain.LoopItem(
                    loop_run_id=loop_run.id,  # type: ignore[arg-type]
                    external_id=str(item_data.get("external_id", processed_count)),
                    title=str(item_data.get("title", f"Loop Item {processed_count}")),
                    payload=item_data,
                    status="ACTIONABLE",
                    idempotency_key=item_key,
                )
                created_item = await self.loop_service.create_loop_item(item)
                created_task = await self._create_task_for_loop_item(
                    loop_def=loop_def,
                    item=created_item,
                    ordinal=processed_count,
                )
                created_item.scheduler_task_id = created_task.id
                created_item.status = "TASK_CREATED"
                await self.loop_service.update_loop_item(created_item)
                processed_count += 1

        loop_run.items_processed = processed_count
        loop_run = await self.loop_service.update_loop_run(loop_run)

        # Update loop status & snapshot
        await self.loop_service.update_loop_status(loop_id, status=LoopStatus.RUNNING)
        await self._update_loop_snapshot(loop_id, active_run_id=loop_run.id)

        await self._log_audit_event(
            project_id=loop_def.project_id,
            details=(
                f"Loop {loop_id} run {loop_run.id} created scheduler Run "
                f"{scheduler_run.id} with {processed_count} actionable items."
            ),
            execution_id=scheduler_run.id,
        )

        return loop_run

    async def trigger_external_event(
        self,
        *,
        loop_id: int,
        provider: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        now: datetime | None = None,
    ) -> domain.LoopRun:
        """Validate and trigger a provider-neutral authenticated external event."""
        loop_def = await self.loop_service.get_loop(loop_id)
        if not loop_def:
            raise ValueError(f"Loop definition with ID {loop_id} not found")
        if loop_def.trigger.kind != TriggerKind.EVENT:
            raise ValueError("External event adapter can only trigger EVENT loops")

        envelope = validate_external_event_envelope(
            loop_id=loop_id,
            provider=provider,
            headers=headers,
            payload=payload,
            safety_policy=loop_def.safety_policy,
            now=now,
        )
        provider_policy = _external_provider_policy(loop_def.safety_policy, provider)
        max_events = int(provider_policy.get("max_events_per_window") or 60)
        replay_window = int(provider_policy.get("replay_window_seconds") or 300)
        recent_count = await self.loop_service.count_loop_runs_since(
            loop_id=loop_id,
            idempotency_prefix=f"external:{loop_id}:{provider}:",
            since=window_start(now, replay_window),
        )
        existing_run = await self.loop_service.get_loop_run_by_idempotency_key(
            envelope.idempotency_key
        )
        if existing_run is None and recent_count >= max_events:
            raise ValueError("External trigger rate limit exceeded for provider window.")

        return await self.trigger_loop(
            loop_id=loop_id,
            trigger_kind=TriggerKind.EVENT,
            idempotency_key=envelope.idempotency_key,
            payload=envelope.payload,
            triggered_at=now,
        )

    async def _create_task_for_loop_item(
        self,
        loop_def: domain.LoopDefinition,
        item: domain.LoopItem,
        ordinal: int,
    ) -> domain.Task:
        payload = item.payload
        task_contract = payload.get("task_contract")
        if not isinstance(task_contract, dict):
            task_contract = {}
        acceptance = payload.get("acceptance_criteria")
        if not isinstance(acceptance, list):
            acceptance = task_contract.get("acceptance_criteria")
        if not isinstance(acceptance, list):
            acceptance = [f"Resolve loop item {item.external_id}: {item.title}"]
        metadata = {
            "source": "loop_item",
            "loop_id": loop_def.id,
            "loop_run_id": item.loop_run_id,
            "loop_item_id": item.id,
            "external_id": item.external_id,
            "task_contract": {
                **task_contract,
                "loop_item_id": item.id,
                "required_evidence": task_contract.get(
                    "required_evidence", ["Task reaches PR_READY through governed scheduler"]
                ),
            },
        }
        key = str(payload.get("key") or f"LOOP-{item.loop_run_id}-{ordinal + 1:03d}")
        return await self.task_service.create_task(
            domain.Task(
                project_id=loop_def.project_id,
                key=key,
                title=str(payload.get("title") or item.title),
                description=str(payload.get("description") or item.title),
                acceptance_criteria=[str(value) for value in acceptance],
                risk_level=str(payload.get("risk_level") or "medium"),
                status=TaskStatus.READY,
                metadata=metadata,
            )
        )

    async def _run_cheap_triage(
        self, loop_def: domain.LoopDefinition, payload: dict[str, Any] | None
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Perform a low-cost triage step to evaluate if actionable work exists.

        Returns (is_actionable, items_list).
        """
        if payload and payload.get("force_actionable"):
            items = payload.get("items", [{"external_id": "item_1", "title": "Manual Action Item"}])
            return True, items

        if payload and payload.get("force_noop"):
            return False, []

        # Default triage logic: if payload has items, it's actionable; otherwise inspect detector
        if payload and "items" in payload:
            items = payload["items"]
            return len(items) > 0, items

        # Production-safe default: no detector/payload means no actionable work.
        return False, []

    async def recover_pending_loops(self, project_id: int) -> list[domain.LoopRun]:
        """Scan and recover any pending or running loop runs after process restart."""
        loops = await self.loop_service.list_loops_for_project(project_id)
        recovered_runs = []

        for loop_def in loops:
            runs = await self.loop_service.list_runs_for_loop(loop_def.id, limit=10)  # type: ignore[arg-type]
            for run in runs:
                if run.status in (LoopRunStatus.TRIAGING, LoopRunStatus.RUNNING):
                    logger.info(f"Recovering pending loop run {run.id} for loop {loop_def.id}")
                    if run.status == LoopRunStatus.TRIAGING:
                        # Re-run triage
                        is_actionable, items = await self._run_cheap_triage(loop_def, None)
                        if not is_actionable:
                            run.status = LoopRunStatus.NO_OP
                            run.triage_verdict = LoopRunVerdict.NO_OP
                            run.completed_at = datetime.now(UTC)
                        else:
                            run.status = LoopRunStatus.RUNNING
                            run.triage_verdict = LoopRunVerdict.ACTIONABLE
                    run = await self.loop_service.update_loop_run(run)
                    recovered_runs.append(run)

        return recovered_runs

    async def pause_loop(self, loop_id: int) -> domain.LoopDefinition:
        """Pause a loop definition and mark active runs as PAUSED."""
        loop_def = await self.loop_service.update_loop_status(loop_id, status=LoopStatus.PAUSED)
        if not loop_def:
            raise ValueError(f"Loop {loop_id} not found")

        runs = await self.loop_service.list_runs_for_loop(loop_id, limit=5)
        for run in runs:
            if run.status == LoopRunStatus.RUNNING:
                run.status = LoopRunStatus.PAUSED
                await self.loop_service.update_loop_run(run)

        await self._log_audit_event(
            project_id=loop_def.project_id,
            details=f"Loop {loop_id} paused",
        )
        return loop_def

    async def resume_loop(self, loop_id: int) -> domain.LoopDefinition:
        """Resume a paused loop definition."""
        loop_def = await self.loop_service.update_loop_status(loop_id, status=LoopStatus.IDLE)
        if not loop_def:
            raise ValueError(f"Loop {loop_id} not found")

        runs = await self.loop_service.list_runs_for_loop(loop_id, limit=5)
        for run in runs:
            if run.status == LoopRunStatus.PAUSED:
                run.status = LoopRunStatus.RUNNING
                await self.loop_service.update_loop_run(run)

        await self._log_audit_event(
            project_id=loop_def.project_id,
            details=f"Loop {loop_id} resumed",
        )
        return loop_def

    async def _log_audit_event(
        self, project_id: int, details: str, execution_id: int | None = None
    ) -> None:
        event = domain.AuditEvent(
            project_id=project_id,
            run_id=execution_id,
            actor_type=AuditEventActorType.SYSTEM,
            actor_id="loop_coordinator",
            event_type=AuditEventType.SYSTEM_EVENT,
            payload_redacted={"details": details},
        )
        await self.audit_service.append_audit_event(event)

    async def _update_loop_snapshot(self, loop_id: int, active_run_id: int | None) -> None:
        runs = await self.loop_service.list_runs_for_loop(loop_id, limit=100)
        total_runs = len(runs)
        total_cost = sum(r.cost_usd for r in runs)
        last_run_at = runs[0].started_at if runs else None

        snapshot = domain.LoopStateSnapshot(
            loop_id=loop_id,
            active_run_id=active_run_id,
            last_run_at=last_run_at,
            total_runs=total_runs,
            total_cost_usd=total_cost,
        )
        await self.loop_service.create_or_update_snapshot(snapshot)

    async def kill_loop_run(
        self,
        run_id: int,
        actor_id: str = "user",
        reason: str = "Manual kill requested",
    ) -> domain.LoopRun:
        """Kill an active or triaging Loop Run, stopping execution and logging audit evidence."""
        run = await self.loop_service.get_loop_run(run_id)
        if not run:
            raise ValueError(f"LoopRun with ID {run_id} not found")

        run.status = LoopRunStatus.CANCELLED
        run.completed_at = datetime.now(UTC)
        run.error_message = f"Killed by {actor_id}: {reason}"
        updated_run = await self.loop_service.update_loop_run(run)

        loop_def = await self.loop_service.get_loop(run.loop_id)
        if loop_def:
            await self._log_audit_event(
                project_id=loop_def.project_id,
                details=f"LoopRun {run_id} killed by {actor_id}: {reason}",
                execution_id=run.scheduler_run_id,
            )
            await self._update_loop_snapshot(run.loop_id, active_run_id=None)

        return updated_run


def _external_provider_policy(safety_policy: dict[str, Any], provider: str) -> dict[str, Any]:
    external = safety_policy.get("external_triggers")
    if isinstance(external, dict):
        provider_policy = external.get(provider)
        if isinstance(provider_policy, dict):
            return provider_policy
    return safety_policy
