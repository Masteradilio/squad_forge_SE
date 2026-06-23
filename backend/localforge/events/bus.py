import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from localforge.models import domain
from localforge.models.enums import AuditEventType
from localforge.storage import DatabaseManager, UnitOfWork

MAX_PAYLOAD_CHARS = 900


@dataclass(frozen=True)
class LifecycleEvent:
    project_id: int
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    run_id: int | None = None
    task_id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def compact(self) -> "LifecycleEvent":
        payload: dict[str, Any] = {}
        budget = MAX_PAYLOAD_CHARS
        for key, value in self.payload.items():
            text = str(value)
            if len(text) > 240:
                value = text[:237] + "..."
            budget -= len(str(key)) + len(str(value))
            if budget <= 0:
                payload["truncated"] = True
                break
            payload[key] = value
        return LifecycleEvent(
            id=self.id,
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=self.task_id,
            event_type=self.event_type,
            payload=payload,
            created_at=self.created_at,
        )

    def to_sse_payload(self) -> dict[str, Any]:
        event = self.compact()
        return {
            "id": event.id,
            "project_id": event.project_id,
            "run_id": event.run_id,
            "task_id": event.task_id,
            "type": event.event_type,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }


class EventBus:
    def __init__(self, *, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._subscribers: dict[int, set[asyncio.Queue[LifecycleEvent]]] = {}
        self._next_memory_id = 1_000_000

    def subscribe(self, project_id: int) -> asyncio.Queue[LifecycleEvent]:
        queue: asyncio.Queue[LifecycleEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    def unsubscribe(self, project_id: int, queue: asyncio.Queue[LifecycleEvent]) -> None:
        queues = self._subscribers.get(project_id)
        if queues:
            queues.discard(queue)

    async def publish(self, event: LifecycleEvent) -> LifecycleEvent:
        if event.id is None:
            event = LifecycleEvent(
                id=self._next_memory_id,
                project_id=event.project_id,
                run_id=event.run_id,
                task_id=event.task_id,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            self._next_memory_id += 1
        for queue in list(self._subscribers.get(event.project_id, set())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event.compact())
        return event

    async def replay(
        self,
        *,
        project_id: int,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[LifecycleEvent]:
        async with UnitOfWork(self.db_manager) as uow:
            assert uow.audits is not None
            events = await uow.audits.list_audit_events_for_project(project_id)
        replayed = [
            map_audit_event(event).compact()
            for event in reversed(events)
            if event.id is not None and event.id > after_id
        ]
        return replayed[:limit]


def map_audit_event(event: domain.AuditEvent) -> LifecycleEvent:
    payload = dict(event.payload_redacted)
    event_type = "system.event"
    if event.event_type == AuditEventType.STATE_CHANGE:
        event_type = "task.status_changed"
    elif event.event_type == AuditEventType.SAFETY_DECISION:
        decision = str(payload.get("decision", "")).upper()
        event_type = "safety.action_allowed" if decision == "ALLOW" else "safety.action_blocked"
    elif event.event_type == AuditEventType.SYSTEM_EVENT:
        event_type = _system_event_name(payload)
    return LifecycleEvent(
        id=event.id,
        project_id=event.project_id,
        run_id=event.run_id,
        task_id=event.task_id,
        event_type=event_type,
        payload=payload,
        created_at=event.created_at,
    )


def _system_event_name(payload: dict[str, Any]) -> str:
    action = str(payload.get("action", ""))
    if action in {"run_start", "run_started"}:
        return "run.started"
    if action in {"action_requested", "approval_requested"}:
        return "agent.action_requested"
    if action in {"test_finished", "test.finished"}:
        return "test.finished"
    if action == "repair_started":
        return "repair.started"
    if action == "repair_succeeded":
        return "repair.succeeded"
    if action in {"repair_failed", "repair_rollback"}:
        return "repair.failed"
    if action in {"pr_created", "pr_artifact_generated"}:
        return "pr.created"
    if action == "artifact_created":
        return "artifact.created"
    return "system.event"
