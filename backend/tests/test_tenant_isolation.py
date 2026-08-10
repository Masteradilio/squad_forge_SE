import pytest
from fastapi.testclient import TestClient

from localforge.api.app import create_app
from localforge.models import domain
from localforge.models.enums import ArtifactType, AuditEventActorType, AuditEventType
from localforge.services.tenant_context import TenantContext, bind_context, reset_context
from localforge.storage.database import DatabaseManager
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage import UnitOfWork


async def _with_tenant(manager, tenant_id: str, user_id: str = "user"):
    token = bind_context(TenantContext(tenant_id=tenant_id, user_id=user_id))
    uow = UnitOfWork(manager)
    await uow.__aenter__()
    return uow, token


async def _close_tenant(uow, token) -> None:
    await uow.__aexit__(None, None, None)
    reset_context(token)


@pytest.mark.asyncio
async def test_projects_tasks_and_runs_are_scoped_to_tenant(db_manager, tmp_path):
    owner_uow, owner_token = await _with_tenant(db_manager, "tenant-a", "alice")
    try:
        assert owner_uow.projects is not None
        assert owner_uow.tasks is not None
        assert owner_uow.executions is not None
        project = await owner_uow.projects.create_project(
            domain.Project(
                name="Tenant A project",
                root_path=str(tmp_path / "a"),
                default_branch="main",
            )
        )
        task = await owner_uow.tasks.create_task(
            domain.Task(
                project_id=project.id,
                key="TENANT-A-1",
                title="Private task",
                description="Must not cross tenant boundary",
            )
        )
        run = await owner_uow.executions.create_run(
            domain.Run(
                project_id=project.id,
                mode=domain.RunMode.UNATTENDED,
                initiated_by="alice",
            )
        )
        task_run = await owner_uow.tasks.create_task_run(
            domain.TaskRun(run_id=run.id, task_id=task.id)
        )
        fact = await owner_uow.memory.create_fact(
            domain.MemoryFact(project_id=project.id, fact="tenant A private memory")
        )
        event = await owner_uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=project.id,
                task_id=task.id,
                actor_type=AuditEventActorType.SYSTEM,
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={"tenant": "a"},
            )
        )
        artifact = await owner_uow.audits.create_artifact(
            domain.Artifact(
                task_run_id=task_run.id,
                type=ArtifactType.TEST,
                path="tenant-a-test.txt",
                content_hash="a" * 64,
                summary="private artifact",
            )
        )
        await owner_uow.commit()
    finally:
        await _close_tenant(owner_uow, owner_token)

    other_uow, other_token = await _with_tenant(db_manager, "tenant-b", "bob")
    try:
        assert other_uow.projects is not None
        assert other_uow.tasks is not None
        assert other_uow.executions is not None
        assert await other_uow.projects.list_projects() == []
        assert await other_uow.projects.get_project(project.id) is None
        assert await other_uow.tasks.get_task(task.id) is None
        assert await other_uow.tasks.list_tasks_for_project(project.id) == []
        assert await other_uow.executions.get_run(run.id) is None
        assert await other_uow.tasks.get_task_run(task_run.id) is None
        assert await other_uow.memory.list_facts(project.id) == []
        assert await other_uow.audits.list_audit_events_for_project(project.id) == []
        assert await other_uow.audits.get_audit_event(event.id) is None
        assert await other_uow.audits.get_artifact(artifact.id) is None
        try:
            await other_uow.audits.create_artifact(
                domain.Artifact(
                    task_run_id=task_run.id,
                    type=ArtifactType.TEST,
                    path="cross-tenant.txt",
                    content_hash="b" * 64,
                )
            )
        except ValueError as exc:
            assert "tenant" in str(exc).lower()
        else:
            raise AssertionError("cross-tenant artifact creation was accepted")
        try:
            await other_uow.tasks.create_task(
                domain.Task(
                    project_id=project.id,
                    key="TENANT-B-1",
                    title="Cross tenant write",
                    description="Must be rejected",
                )
            )
        except ValueError as exc:
            assert "tenant" in str(exc).lower()
        else:
            raise AssertionError("cross-tenant task creation was accepted")
    finally:
        await _close_tenant(other_uow, other_token)


def test_api_tenant_headers_hide_cross_tenant_projects(tmp_path):
    import asyncio

    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'api-tenants.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    try:
        app = create_app(manager)
        tenant_a = {"x-tenant-id": "tenant-a", "x-user-id": "alice"}
        tenant_b = {"x-tenant-id": "tenant-b", "x-user-id": "bob"}
        with TestClient(app) as client:
            created = client.post(
                "/projects",
                headers=tenant_a,
                json={"name": "A", "root_path": str(tmp_path / "a"), "default_branch": "main"},
            )
            assert created.status_code == 200
            project_id = created.json()["id"]
            assert client.get("/projects", headers=tenant_a).json()[0]["tenant_id"] == "tenant-a"
            assert client.get("/projects", headers=tenant_b).json() == []
            assert client.get(f"/projects/{project_id}/tasks", headers=tenant_b).json() == []
    finally:
        asyncio.run(manager.close())
