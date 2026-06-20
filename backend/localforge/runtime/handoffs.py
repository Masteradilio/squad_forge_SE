from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    AuditEventActorType,
    AuditEventType,
    HandoffKind,
    HandoffStatus,
)
from localforge.storage import UnitOfWork


class RuntimeHandoffService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        project_id: int,
        run_id: int | None = None,
        task_id: int | None = None,
    ):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id
        self.task_id = task_id

    async def create(
        self,
        *,
        task_run_id: int,
        from_role: AgentRole,
        to_role: AgentRole,
        kind: HandoffKind,
        payload: dict[str, object],
    ) -> domain.Handoff:
        assert self.uow.executions is not None
        handoff = await self.uow.executions.create_handoff(
            domain.Handoff(
                task_run_id=task_run_id,
                from_role=from_role,
                to_role=to_role,
                kind=kind,
                payload_json=payload,
            )
        )
        await self._audit("handoff_created", handoff)
        return handoff

    async def consume_once(self, handoff_id: int | None) -> domain.Handoff:
        if handoff_id is None:
            raise ValueError("Cannot consume a handoff without an ID.")
        assert self.uow.executions is not None
        current = await self.uow.executions.get_handoff(handoff_id)
        if not current:
            raise ValueError(f"Handoff with ID {handoff_id} not found.")
        if current.status != HandoffStatus.PENDING:
            raise ValueError(f"Handoff {handoff_id} has already been consumed.")
        consumed = await self.uow.executions.consume_handoff(handoff_id)
        await self._audit("handoff_consumed", consumed)
        return consumed

    async def _audit(self, action: str, handoff: domain.Handoff) -> None:
        assert self.uow.audits is not None
        await self.uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=self.task_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="runtime-handoff",
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={
                    "action": action,
                    "handoff_id": handoff.id,
                    "from_role": handoff.from_role.value,
                    "to_role": handoff.to_role.value,
                    "kind": handoff.kind.value,
                },
            )
        )
