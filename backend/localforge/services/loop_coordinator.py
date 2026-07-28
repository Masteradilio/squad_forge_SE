import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import (
    AuditEventActorType,
    AuditEventType,
    LoopRunStatus,
    LoopRunVerdict,
    LoopStatus,
    RunMode,
    RunStatus,
    TriggerKind,
)
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.loop_service import LoopService

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

    async def trigger_loop(
        self,
        loop_id: int,
        trigger_kind: TriggerKind = TriggerKind.MANUAL,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> domain.LoopRun:
        """Receive a trigger for a loop, enforce idempotency, run triage, and manage run lifecycle."""
        loop_def = await self.loop_service.get_loop(loop_id)
        if not loop_def:
            raise ValueError(f"Loop definition with ID {loop_id} not found")

        if not loop_def.enabled or loop_def.status == LoopStatus.DISABLED:
            raise ValueError(f"Loop {loop_id} is disabled and cannot be executed")

        if loop_def.status == LoopStatus.PAUSED:
            raise ValueError(f"Loop {loop_id} is currently paused")

        key = idempotency_key or f"loop_{loop_id}_{trigger_kind}_{datetime.now(UTC).timestamp()}"

        # Deduplication check
        existing_run = await self.loop_service.get_loop_run_by_idempotency_key(key)
        if existing_run:
            logger.info(f"Duplicate trigger received for loop {loop_id} with key {key}. Returning existing run.")
            return existing_run

        # Create LoopRun record in PENDING state
        loop_run = domain.LoopRun(
            loop_id=loop_id,
            status=LoopRunStatus.TRIAGING,
            trigger_kind=trigger_kind,
            idempotency_key=key,
            triage_verdict=LoopRunVerdict.PENDING,
        )
        loop_run = await self.loop_service.create_loop_run(loop_run)

        # Audit trigger receipt
        await self._log_audit_event(
            project_id=loop_def.project_id,
            details=f"Loop {loop_id} triggered via {trigger_kind} (key: {key})",
        )

        # Run cheap triage
        is_actionable, items = await self._run_cheap_triage(loop_def, payload)

        if not is_actionable:
            # Triage verdict: NO_OP
            loop_run.status = LoopRunStatus.NO_OP
            loop_run.triage_verdict = LoopRunVerdict.NO_OP
            loop_run.completed_at = datetime.now(UTC)
            loop_run = await self.loop_service.update_loop_run(loop_run)

            await self._log_audit_event(
                project_id=loop_def.project_id,
                details=f"Loop {loop_id} run {loop_run.id} triaged as NO_OP. No scheduler run created.",
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
            status=RunStatus.RUNNING,
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
                await self.loop_service.create_loop_item(item)
                processed_count += 1

        loop_run.items_processed = processed_count
        loop_run = await self.loop_service.update_loop_run(loop_run)

        # Update loop status & snapshot
        await self.loop_service.update_loop_status(loop_id, status=LoopStatus.RUNNING)
        await self._update_loop_snapshot(loop_id, active_run_id=loop_run.id)

        await self._log_audit_event(
            project_id=loop_def.project_id,
            details=f"Loop {loop_id} run {loop_run.id} created scheduler Run {scheduler_run.id} with {processed_count} actionable items.",
            execution_id=scheduler_run.id,
        )


        return loop_run

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

        # Simple default detector fallback: if manually triggered without payload, treat as single actionable item
        return True, [{"external_id": "task_1", "title": f"Action for {loop_def.name}"}]

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

