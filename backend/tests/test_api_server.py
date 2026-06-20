import asyncio

from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.models import domain
from localforge.models.enums import AgentRole, ArtifactType, RunMode, RunStatus, TaskStatus
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager
from localforge.storage.orm import ArtifactORM


def test_api_health_and_openapi_available(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        client = TestClient(create_app(db_manager=manager))
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/openapi.json").status_code == 200
    finally:
        close_manager(manager)


def test_api_exposes_core_state_endpoints(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        assert client.get("/projects").json()[0]["id"] == ids["project_id"]
        assert client.get(f"/projects/{ids['project_id']}/tasks").json()[0]["key"] == "LF-1401"
        assert client.get(f"/projects/{ids['project_id']}/runs").json()[0]["id"] == ids["run_id"]
        assert client.get("/agents").json()[0]["name"] == "tester"
        assert client.get(f"/tasks/{ids['task_id']}/artifacts").json()[0]["type"] == "TestArtifact"
        assert (
            client.get(f"/projects/{ids['project_id']}/policies/default").json()["name"]
            == "default"
        )
        assert client.get("/models").json()["provider"] == "localforge"
        assert client.get(f"/projects/{ids['project_id']}/prs").json()[0]["key"] == "LF-1401"
    finally:
        close_manager(manager)


def test_api_command_bridge_updates_runs_and_audits(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        response = client.post(f"/runs/{ids['run_id']}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "PAUSED"
        events = client.get(f"/projects/{ids['project_id']}/audit-events").json()
        assert any(event["payload_redacted"]["action"] == "run_pause" for event in events)
    finally:
        close_manager(manager)


def test_api_artifact_content_redacts_secrets_and_blocks_traversal(tmp_path, monkeypatch):
    manager = make_db_manager(tmp_path)
    try:
        monkeypatch.setenv("LOCALFORGE_GITHUB_TOKEN", "secret-token")
        ids = seed_api_state(manager, tmp_path, content="token=secret-token\n")
        client = TestClient(create_app(db_manager=manager))

        response = client.get(f"/artifacts/{ids['artifact_id']}/content")

        assert response.status_code == 200
        assert "secret-token" not in response.json()["content"]
        assert "[REDACTED]" in response.json()["content"]

        poison_artifact_path(manager, ids["artifact_id"])
        blocked = client.get(f"/artifacts/{ids['artifact_id']}/content")
        assert blocked.status_code == 403
    finally:
        close_manager(manager)


def make_db_manager(tmp_path) -> DatabaseManager:
    db_file = (tmp_path / "api.db").as_posix()
    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_file}")
    asyncio.run(bootstrap_database(manager))
    return manager


def close_manager(manager: DatabaseManager) -> None:
    asyncio.run(manager.close())


def seed_api_state(
    db_manager: DatabaseManager, tmp_path, content: str = "tests passed\n"
) -> dict[str, int]:
    async def seed() -> dict[str, int]:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            assert uow.tasks is not None
            assert uow.executions is not None
            assert uow.audits is not None
            project = await uow.projects.create_project(
                domain.Project(name="API", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            await uow.audits.create_policy(
                domain.Policy(project_id=project.id, name="default", rules={"protected_paths": []})
            )
            task = await uow.tasks.create_task(
                domain.Task(
                    project_id=project.id,
                    key="LF-1401",
                    title="API",
                    description="Expose state",
                    status=TaskStatus.PR_READY,
                )
            )
            assert task.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.INTERACTIVE,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                )
            )
            assert run.id is not None
            agent = await uow.executions.register_agent(
                domain.Agent(name="tester", role=AgentRole.TESTER, model_profile_id="fake")
            )
            assert agent.id is not None
            task_run = await uow.tasks.create_task_run(
                domain.TaskRun(run_id=run.id, task_id=task.id)
            )
            assert task_run.id is not None
            artifact_dir = tmp_path / ".localforge" / "artifacts"
            artifact_dir.mkdir(parents=True)
            artifact_file = artifact_dir / "tests.md"
            artifact_file.write_text(content, encoding="utf-8")
            artifact = await uow.audits.create_artifact(
                domain.Artifact(
                    task_run_id=task_run.id,
                    type=ArtifactType.TEST,
                    path=".localforge/artifacts/tests.md",
                    content_hash="hash",
                    summary="tests",
                )
            )
            assert artifact.id is not None
            return {
                "project_id": project.id,
                "task_id": task.id,
                "run_id": run.id,
                "artifact_id": artifact.id,
            }

    return asyncio.run(seed())


def poison_artifact_path(db_manager: DatabaseManager, artifact_id: int) -> None:
    async def poison() -> None:
        async with await db_manager.get_session() as session:
            artifact = await session.get(ArtifactORM, artifact_id)
            assert artifact is not None
            artifact.path = "../outside.txt"
            await session.commit()

    asyncio.run(poison())
