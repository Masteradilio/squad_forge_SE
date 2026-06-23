import asyncio
import json

from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.models import domain
from localforge.models.enums import (
    ArtifactType,
    MemoryRecordKind,
    RunMode,
    RunStatus,
    TaskStatus,
)
from localforge.runtime.context import TaskContextBuilder
from localforge.skills import SkillRegistry
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_skill_registry_loads_builtins_and_local_skills(tmp_path):
    project_root = tmp_path
    skill_dir = project_root / ".localforge" / "skills"
    skill_dir.mkdir(parents=True)
    (skill_dir / "sqlite-migration.json").write_text(
        json.dumps(
            {
                "name": "sqlite-migration",
                "purpose": "Plan SQLite migrations safely.",
                "triggers": ["sqlite", "migration"],
                "allowed_actions": ["read schema"],
                "expected_artifacts": ["risk.md"],
                "failure_modes": ["missing migration"],
                "examples": ["Add nullable column first."],
            }
        ),
        encoding="utf-8",
    )

    registry = SkillRegistry(str(project_root))
    names = {skill.name for skill in registry.load_all()}
    selected = registry.select_for_task(
        domain.Task(
            project_id=1,
            key="LF-2401",
            title="SQLite migration",
            description="Add sqlite migration support",
            status=TaskStatus.READY,
        )
    )

    assert "python-pytest" in names
    assert "sqlite-migration" in names
    assert [skill.name for skill in selected] == ["sqlite-migration"]


def test_task_context_includes_selected_skills_and_relevant_memory(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_state(manager, tmp_path)

        async def exercise() -> str:
            async with UnitOfWork(manager) as uow:
                assert uow.memory is not None
                await uow.memory.create_fact(
                    domain.MemoryFact(
                        project_id=ids["project_id"],
                        kind=MemoryRecordKind.KNOWN_PITFALL,
                        fact="FastAPI endpoints need explicit 404 paths.",
                        pinned=True,
                        tags=["fastapi", "endpoint"],
                    )
                )
                return (
                    await TaskContextBuilder(uow).build(
                        ids["task_id"],
                        str(tmp_path),
                        max_chars=2_000,
                    )
                ).rendered

        rendered = asyncio.run(exercise())

        assert "fastapi-endpoint" in rendered
        assert "FastAPI endpoints need explicit 404 paths" in rendered
    finally:
        close_manager(manager)


def test_memory_learns_safe_facts_from_completed_runs(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_state(manager, tmp_path)

        async def exercise() -> list[str]:
            async with UnitOfWork(manager) as uow:
                assert uow.memory is not None
                learned = await uow.memory.learn_from_completed_run(
                    project_id=ids["project_id"],
                    task_key="LF-2504",
                    task_title="Memory",
                    final_summary="Resolved flaky pytest command by narrowing scope.",
                    artifact_summaries=[
                        (ArtifactType.TEST, "python -m pytest backend/tests/test_api_server.py -q"),
                        (ArtifactType.RISK, "Avoid broad test suite during iteration."),
                    ],
                )
                return [fact.kind.value for fact in learned]

        kinds = asyncio.run(exercise())

        assert MemoryRecordKind.RESOLVED_BLOCKER.value in kinds
        assert MemoryRecordKind.TEST_COMMAND.value in kinds
        assert MemoryRecordKind.KNOWN_PITFALL.value in kinds
    finally:
        close_manager(manager)


def test_skills_api_registers_local_skill(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        created = client.post(
            f"/projects/{ids['project_id']}/skills",
            json={
                "name": "sqlite-migration",
                "purpose": "Plan SQLite migrations safely.",
                "triggers": ["sqlite"],
                "allowed_actions": ["read schema"],
                "expected_artifacts": ["risk.md"],
                "failure_modes": ["missing migration"],
                "examples": ["Prefer additive migration."],
            },
        )
        listed = client.get(f"/projects/{ids['project_id']}/skills")

        assert created.status_code == 200
        assert created.json()["source"] == "local"
        assert any(skill["name"] == "sqlite-migration" for skill in listed.json())
    finally:
        close_manager(manager)


def make_db_manager(tmp_path) -> DatabaseManager:
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase2425.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    return manager


def close_manager(manager: DatabaseManager) -> None:
    asyncio.run(manager.close())


def seed_state(db_manager: DatabaseManager, tmp_path) -> dict[str, int]:
    async def seed() -> dict[str, int]:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            assert uow.tasks is not None
            assert uow.executions is not None
            project = await uow.projects.create_project(
                domain.Project(name="Phase 24", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            task = await uow.tasks.create_task(
                domain.Task(
                    project_id=project.id,
                    key="LF-2403",
                    title="FastAPI endpoint",
                    description="Add FastAPI endpoint skills support",
                    status=TaskStatus.READY,
                    metadata={"stack": ["fastapi", "pytest"]},
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
            return {"project_id": project.id, "task_id": task.id, "run_id": run.id}

    return asyncio.run(seed())
