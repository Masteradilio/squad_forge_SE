import asyncio
import json

from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.events.bus import EventBus, LifecycleEvent, map_audit_event
from localforge.models import domain
from localforge.models.enums import AuditEventActorType, AuditEventType
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_event_bus_supports_publish_subscribe_and_audit_replay(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_event_state(manager, tmp_path)

        async def exercise() -> list[LifecycleEvent]:
            bus = EventBus(db_manager=manager)
            subscriber = bus.subscribe(project_id=ids["project_id"])
            await bus.publish(
                LifecycleEvent(
                    project_id=ids["project_id"],
                    event_type="run.started",
                    payload={"run_id": ids["run_id"]},
                )
            )
            received = await asyncio.wait_for(subscriber.get(), timeout=1.0)
            replayed = await bus.replay(project_id=ids["project_id"], after_id=0)
            return [received, *replayed]

        events = asyncio.run(exercise())

        assert events[0].event_type == "run.started"
        assert any(event.event_type == "task.status_changed" for event in events)
    finally:
        close_manager(manager)


def test_sse_endpoint_streams_replay_with_small_payloads(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_event_state(manager, tmp_path)
        app = create_app(db_manager=manager)
        client = TestClient(app)

        with client.stream("GET", f"/projects/{ids['project_id']}/events?limit=1") as response:
            assert response.status_code == 200
            lines = response.iter_lines()
            first_line = next(lines)
            assert first_line.startswith("id:")
            event_line = next(lines)
            assert event_line.startswith("event:")
            data_line = next(lines)
            assert data_line.startswith("data:")
            payload = json.loads(data_line.removeprefix("data: "))
            assert len(json.dumps(payload)) < 1200
    finally:
        close_manager(manager)


def test_sse_reconnect_uses_last_event_id_for_replay(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_event_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        with client.stream(
            "GET", f"/projects/{ids['project_id']}/events?last_event_id={ids['audit_id']}"
        ) as response:
            assert response.status_code == 200
            lines = []
            for line in response.iter_lines():
                lines.append(line)
                if line.startswith("data:"):
                    break
            assert not any("task.status_changed" in line for line in lines)
    finally:
        close_manager(manager)


def test_audit_event_mapping_covers_required_lifecycle_names():
    assert (
        map_audit_event(
            domain.AuditEvent(
                project_id=1,
                actor_type=AuditEventActorType.SYSTEM,
                event_type=AuditEventType.STATE_CHANGE,
                payload_redacted={"task_id": 2, "to_status": "READY"},
            )
        ).event_type
        == "task.status_changed"
    )
    assert (
        map_audit_event(
            domain.AuditEvent(
                project_id=1,
                actor_type=AuditEventActorType.SYSTEM,
                event_type=AuditEventType.SAFETY_DECISION,
                payload_redacted={"decision": "ALLOW"},
            )
        ).event_type
        == "safety.action_allowed"
    )
    assert (
        map_audit_event(
            domain.AuditEvent(
                project_id=1,
                actor_type=AuditEventActorType.SYSTEM,
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={"action": "repair_rollback"},
            )
        ).event_type
        == "repair.failed"
    )


def make_db_manager(tmp_path) -> DatabaseManager:
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'events.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    return manager


def close_manager(manager: DatabaseManager) -> None:
    asyncio.run(manager.close())


def seed_event_state(db_manager: DatabaseManager, tmp_path) -> dict[str, int]:
    async def seed() -> dict[str, int]:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            assert uow.tasks is not None
            assert uow.audits is not None
            project = await uow.projects.create_project(
                domain.Project(name="Events", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=domain.RunMode.INTERACTIVE,
                    initiated_by="test",
                )
            )
            assert run.id is not None
            task = await uow.tasks.create_task(
                domain.Task(project_id=project.id, key="LF-1501", title="Events", description="")
            )
            assert task.id is not None
            event = await uow.audits.append_audit_event(
                domain.AuditEvent(
                    project_id=project.id,
                    run_id=run.id,
                    task_id=task.id,
                    actor_type=AuditEventActorType.SYSTEM,
                    event_type=AuditEventType.STATE_CHANGE,
                    payload_redacted={"task_id": task.id, "to_status": "READY"},
                )
            )
            assert event.id is not None
            return {
                "project_id": project.id,
                "run_id": run.id,
                "task_id": task.id,
                "audit_id": event.id,
            }

    return asyncio.run(seed())
