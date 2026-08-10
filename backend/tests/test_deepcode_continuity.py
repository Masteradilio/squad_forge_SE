from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.cli.main import app as cli_app
from localforge.models import domain
from localforge.models.enums import (
    ActionKind,
    AuditEventType,
    EngineeringSessionStatus,
    ExecutionMode,
    ProfileDecision,
)
from localforge.services.engineering import (
    EngineeringImmutableTurn,
    EngineeringInvalidTransition,
)
from localforge.services.tenant_context import TenantContext, bind_context, reset_context
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import CURRENT_VERSION, bootstrap_database
from localforge.storage.database import DatabaseManager
from localforge.storage.orm import (
    Base,
    SchemaVersionORM,
)
from sqlalchemy import text
from typer.testing import CliRunner


async def _create_project(manager, tmp_path, tenant_id: str = "tenant-a"):
    token = bind_context(TenantContext(tenant_id=tenant_id, user_id="tester"))
    try:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            project = await uow.projects.create_project(
                domain.Project(
                    name=f"Project {tenant_id}",
                    root_path=str(tmp_path / tenant_id),
                    default_branch="main",
                )
            )
            await uow.commit()
            return project
    finally:
        reset_context(token)


@pytest.mark.asyncio
async def test_continuity_persists_restart_revisions_and_immutable_turns(db_manager, tmp_path):
    project = await _create_project(db_manager, tmp_path)
    token = bind_context(TenantContext(tenant_id="tenant-a", user_id="alice"))
    try:
        async with UnitOfWork(db_manager) as uow:
            assert uow.engineering is not None
            session = await uow.engineering.create_session(
                project_id=project.id,
                title="Durable work",
                default_model="model-v1",
                max_turns=4,
            )
            goal = await uow.engineering.create_goal(
                session_id=session.id,
                objective="Ship the continuity slice",
                acceptance_criteria=["restarts safely"],
            )
            first = await uow.engineering.admit_turn(
                session_id=session.id,
                input_text="inspect",
                model="model-v1",
                idempotency_key="turn-1",
            )
            duplicate = await uow.engineering.admit_turn(
                session_id=session.id,
                input_text="must not replace original",
                model="model-v2",
                idempotency_key="turn-1",
            )
            assert duplicate.id == first.id
            assert duplicate.input_text == "inspect"
            revised = await uow.engineering.revise_goal(
                goal.id,
                "Ship the tested continuity slice",
                ["restarts safely", "keeps the profile snapshot"],
                expected_revision=1,
            )
            second = await uow.engineering.admit_turn(
                session_id=session.id,
                input_text="continue",
                idempotency_key="turn-2",
            )
            assert first.sequence == 1
            assert second.sequence == 2
            assert first.goal_revision_snapshot == 1
            assert second.goal_revision_snapshot == revised.revision == 2
            assert first.profile_snapshot["mode"] == "ASK"
            await uow.commit()

        async with UnitOfWork(db_manager) as reopened:
            assert reopened.engineering is not None
            restored = await reopened.engineering.get_session(session.id)
            timeline = await reopened.engineering.timeline(session.id)
            restored_goal = await reopened.engineering.get_current_goal(session.id)
            assert restored is not None
            assert restored.status == EngineeringSessionStatus.ACTIVE
            assert [item.sequence for item in timeline] == [1, 2]
            assert restored_goal is not None
            assert restored_goal.revision == 2
            with pytest.raises(EngineeringImmutableTurn):
                await reopened.engineering.update_turn(first.id, input_text="mutate")
            with pytest.raises(EngineeringImmutableTurn):
                await reopened.engineering.delete_turn(first.id)
    finally:
        reset_context(token)


@pytest.mark.asyncio
async def test_state_machine_limits_and_audit_are_persistent(db_manager, tmp_path):
    project = await _create_project(db_manager, tmp_path)
    token = bind_context(TenantContext(tenant_id="tenant-a", user_id="alice"))
    try:
        async with UnitOfWork(db_manager) as uow:
            assert uow.engineering is not None and uow.audits is not None
            session = await uow.engineering.create_session(project_id=project.id, max_turns=1)
            await uow.engineering.transition_session(session.id, EngineeringSessionStatus.ACTIVE)
            await uow.engineering.pause_session(session.id, reason="operator pause")
            await uow.engineering.resume_session(session.id, reason="operator resume")
            await uow.engineering.admit_turn(
                session_id=session.id, input_text="one", idempotency_key="only-turn"
            )
            with pytest.raises(Exception, match="continuation policy"):
                await uow.engineering.admit_turn(
                    session_id=session.id, input_text="two", idempotency_key="over-limit"
                )
            await uow.engineering.cancel_session(session.id, reason="done for test")
            with pytest.raises(EngineeringInvalidTransition):
                await uow.engineering.resume_session(session.id)
            events = await uow.audits.list_audit_events_for_project(project.id)
            payloads = [event.payload_redacted for event in events]
            assert any(payload.get("operation") == "transition" for payload in payloads)
            assert any(payload.get("operation") == "turn_limit_rejected" for payload in payloads)
            assert all(event.event_type in {AuditEventType.STATE_CHANGE, AuditEventType.SYSTEM_EVENT} for event in events)
    finally:
        reset_context(token)


@pytest.mark.asyncio
async def test_profile_precedence_approval_replay_and_safety_deny(db_manager, tmp_path):
    project = await _create_project(db_manager, tmp_path)
    token = bind_context(TenantContext(tenant_id="tenant-a", user_id="alice"))
    try:
        async with UnitOfWork(db_manager) as uow:
            assert uow.engineering is not None
            session = await uow.engineering.create_session(project_id=project.id)
            await uow.engineering.create_or_update_profile(
                project_id=project.id,
                session_id=session.id,
                mode=ExecutionMode.FULL_ACCESS,
                tool_policies={"read_file": ProfileDecision.DENY, "write_file": "ask"},
            )
            denied = await uow.engineering.evaluate_action(
                project_id=project.id,
                session_id=session.id,
                action_kind=ActionKind.READ_FILE,
                payload={"path": str(tmp_path / "tenant-a" / "safe.txt")},
            )
            assert denied.decision == "deny"

            asked = await uow.engineering.evaluate_action(
                project_id=project.id,
                session_id=session.id,
                action_kind=ActionKind.WRITE_FILE,
                payload={"path": str(tmp_path / "tenant-a" / "safe.txt")},
                idempotency_key="approval-1",
            )
            asked_again = await uow.engineering.evaluate_action(
                project_id=project.id,
                session_id=session.id,
                action_kind=ActionKind.WRITE_FILE,
                payload={"path": str(tmp_path / "tenant-a" / "safe.txt")},
                idempotency_key="approval-1",
            )
            assert asked.decision == asked_again.decision == "ask"
            assert asked.approval_id == asked_again.approval_id

            allowed = await uow.engineering.evaluate_action(
                project_id=project.id,
                session_id=session.id,
                action_kind=ActionKind.READ_FILE,
                payload={"path": str(tmp_path / "tenant-a" / "other.txt")},
                idempotency_key="read-1",
            )
            assert allowed.decision == "deny"  # explicit deny outranks any mode

            safety_denied = await uow.engineering.evaluate_action(
                project_id=project.id,
                session_id=session.id,
                action_kind=ActionKind.WRITE_FILE,
                payload={"path": str(tmp_path / "outside.txt")},
                idempotency_key="outside-1",
            )
            assert safety_denied.decision == "deny"
            assert safety_denied.safety_decision == "DENY"
    finally:
        reset_context(token)


@pytest.mark.asyncio
async def test_new_and_v22_migrated_databases_have_dpc_tables(tmp_path):
    fresh = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    await bootstrap_database(fresh)
    try:
        async with fresh.engine.connect() as connection:
            names = set(
                (
                    await connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                ).scalars()
            )
        assert {
            "engineering_sessions",
            "engineering_goals",
            "engineering_turns",
            "execution_profiles",
        }.issubset(names)
    finally:
        await fresh.close()

    legacy = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'v22.db').as_posix()}")
    async with legacy.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[
                    SchemaVersionORM.__table__,
                    # The migration path only needs the version table for v22;
                    # create_all will add the complete current metadata.
                ],
            )
        )
    async with await legacy.get_session() as session:
        session.add(SchemaVersionORM(version=22))
        await session.commit()
    try:
        assert await bootstrap_database(legacy) == CURRENT_VERSION
        async with legacy.engine.connect() as connection:
            names = set(
                (
                    await connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                ).scalars()
            )
        assert {
            "engineering_sessions",
            "engineering_goals",
            "engineering_turns",
            "execution_profiles",
        }.issubset(names)
    finally:
        await legacy.close()


def test_api_cli_share_continuity_service_and_isolate_tenants(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    try:
        app = create_app(manager)
        headers_a = {"x-tenant-id": "tenant-a", "x-user-id": "alice"}
        headers_b = {"x-tenant-id": "tenant-b", "x-user-id": "bob"}
        with TestClient(app) as client:
            project_response = client.post(
                "/projects",
                headers=headers_a,
                json={
                    "name": "API project",
                    "root_path": str(tmp_path / "tenant-a"),
                    "default_branch": "main",
                },
            )
            assert project_response.status_code == 200
            project_id = project_response.json()["id"]
            created = client.post(
                f"/projects/{project_id}/engineering/sessions",
                headers=headers_a,
                json={"title": "API session"},
            )
            assert created.status_code == 201
            session_id = created.json()["id"]
            goal = client.post(
                f"/engineering/sessions/{session_id}/goals",
                headers=headers_a,
                json={"objective": "API continuity", "acceptance_criteria": ["works"]},
            )
            assert goal.status_code == 201
            first = client.post(
                f"/engineering/sessions/{session_id}/turns",
                headers=headers_a,
                json={"input_text": "hello", "idempotency_key": "api-1"},
            )
            second = client.post(
                f"/engineering/sessions/{session_id}/turns",
                headers=headers_a,
                json={"input_text": "different", "idempotency_key": "api-1"},
            )
            assert first.status_code == second.status_code == 201
            assert first.json()["id"] == second.json()["id"]
            assert client.get(
                f"/engineering/sessions/{session_id}/timeline", headers=headers_a
            ).json()[0]["sequence"] == 1
            assert client.get(
                f"/engineering/sessions/{session_id}", headers=headers_b
            ).status_code == 404
            assert client.get(
                f"/projects/{project_id}/engineering/sessions", headers=headers_b
            ).json() == []

        from localforge.cli import engineering as engineering_cli

        old_manager = engineering_cli.db_manager
        engineering_cli.db_manager = manager
        try:
            runner = CliRunner()
            result = runner.invoke(
                cli_app,
                [
                    "engineering",
                    "session",
                    "list",
                    "--project-id",
                    str(project_id),
                    "--tenant-id",
                    "tenant-a",
                ],
            )
            assert result.exit_code == 0, result.stdout
            assert json.loads(result.stdout)[0]["id"] == session_id
        finally:
            engineering_cli.db_manager = old_manager
    finally:
        asyncio.run(manager.close())
