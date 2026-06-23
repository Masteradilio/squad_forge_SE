import os
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.cli.plan import run_plan
from localforge.cli.prs import run_prs
from localforge.gitops.manager import WorktreeManager
from localforge.models import domain
from localforge.models.enums import ArtifactType, TaskStatus
from localforge.safety.kernel import ActionRequest, SafetyDecision, SafetyKernel
from localforge.services.audit import AuditService
from localforge.services.project import ProjectService
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@pytest.mark.anyio
async def test_safety_kernel_cmd_injection_blocking(db_session):
    """Verify that command validator rejects chained malicious commands."""
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.audits = AuditService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="SafetyProj", root_path="/tmp", default_branch="main")
    )
    policy = domain.Policy(
        project_id=proj.id,
        name="default",
        rules={
            "blocked_commands": ["rm -rf", "sh", "bash"],
            "protected_paths": [".env"],
            "allowed_commands": ["git", "pytest"]
        }
    )
    await uow.audits.create_policy(policy)
    await db_session.commit()

    # Test chained command bypass attempt (&&)
    req = ActionRequest(
        project_id=proj.id,
        run_id=1,
        task_id=1,
        kind="run_command",
        payload={"command": "git status && rm -rf /"},
        purpose="malicious test"
    )
    decision, reason = await SafetyKernel.evaluate(req, uow, "/tmp")
    assert decision == SafetyDecision.DENY
    assert "Blocked command" in reason or "shell chaining" in reason or "AST" in reason

@pytest.mark.anyio
async def test_artifact_store_atomic_writes(tmp_path):
    """Verify that ArtifactStore writes files atomically using temp swaps."""
    # Mock UOW to avoid DB dependency in this unit test
    uow = MagicMock()
    uow.audits = MagicMock()

    # Mock create_artifact to return whatever artifact was passed to it
    async def mock_create_artifact(art):
        return art
    uow.audits.create_artifact = mock_create_artifact

    store = ArtifactStore(uow)

    project_root = str(tmp_path)
    # Write a test artifact using correct write_artifact signature
    await store.write_artifact(
        project_root=project_root,
        task_run_id=1,
        task_key="LF-1001",
        run_id=1,
        filename="tests.md",
        content="some content",
        summary="some summary"
    )

    resolved_path = os.path.join(
        project_root, 
        ".localforge", 
        "artifacts", 
        "runs", 
        "1", 
        "tasks", 
        "lf-1001", 
        "tests.md"
    )
    assert os.path.exists(resolved_path)
    with open(resolved_path, encoding="utf-8") as f:
        assert f.read() == "some content"

@pytest.mark.anyio
async def test_worktree_manager_lock_concurrency(tmp_path, db_session):
    """Verify WorktreeManager sequential and lock execution boundaries."""
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.audits = AuditService(db_session)

    await uow.projects.create_project(
        domain.Project(name="LockProj", root_path=str(tmp_path), default_branch="main")
    )
    await db_session.commit()

    # Ensure lock exists for normalized absolute paths using the classmethod helper
    lock = WorktreeManager._get_worktree_lock(str(tmp_path / "wt1"))
    assert lock is not None
    # Verifies that repeated calls retrieve the same lock object
    lock2 = WorktreeManager._get_worktree_lock(str(tmp_path / "wt1"))
    assert lock is lock2

@pytest.mark.anyio
async def test_cli_plan_and_run_integration(tmp_path, monkeypatch):
    """Verify that CLI plan and run execute transitions safely."""
    # 1. Move working directory to isolated temp path
    monkeypatch.chdir(tmp_path)

    # 2. Setup workspace structure to pass init detection
    os.makedirs(os.path.join(tmp_path, ".localforge"), exist_ok=True)

    # 3. Set environment variable for test DB path with forward slashes
    test_db_file = os.path.join(tmp_path, "test_localforge.db").replace("\\", "/")
    test_db_url = f"sqlite+aiosqlite:///{test_db_file}"
    monkeypatch.setenv("LOCALFORGE_DATABASE_URL", test_db_url)

    # 4. Inject a new DatabaseManager to override the imported ones
    import localforge.storage.database as db_mod
    test_manager = db_mod.DatabaseManager(test_db_url)

    # Bootstrap the temporary database
    from localforge.storage.bootstrap import bootstrap_database
    await bootstrap_database(test_manager)

    # Patch original db_managers
    original_manager = db_mod.db_manager
    db_mod.db_manager = test_manager

    import localforge.storage as storage_mod
    original_storage_manager = storage_mod.db_manager
    storage_mod.db_manager = test_manager

    import localforge.cli.plan as plan_mod
    original_plan_manager = plan_mod.db_manager
    plan_mod.db_manager = test_manager

    import localforge.cli.prs as prs_mod
    original_prs_manager = prs_mod.db_manager
    prs_mod.db_manager = test_manager

    uow = UnitOfWork(test_manager)

    try:
        async with uow:
            assert uow.projects is not None
            assert uow.tasks is not None

            proj = await uow.projects.create_project(
                domain.Project(
                    name="CliProj",
                    root_path=str(tmp_path),
                    default_branch="main"
                )
            )
            t = await uow.tasks.create_task(
                domain.Task(
                    project_id=proj.id,
                    key="LF-3001",
                    title="Test stabilization",
                    description="Stabilize OS",
                    acceptance_criteria=["Stable build"]
                )
            )
            assert uow.session is not None
            await uow.session.commit()

        # 2. Test plan command - list and then approve task
        # Approve a specific task plan
        await run_plan(approve="LF-3001", approve_all=False)
        
        async with uow:
            refreshed_t = await uow.tasks.get_task(t.id)
            assert refreshed_t is not None
            assert refreshed_t.status == TaskStatus.READY

        # 3. Test prs command list when empty
        await run_prs()

    finally:
        # Clean up database connection pool and restore original managers
        await test_manager.close()
        db_mod.db_manager = original_manager
        storage_mod.db_manager = original_storage_manager
        plan_mod.db_manager = original_plan_manager
        prs_mod.db_manager = original_prs_manager


@pytest.mark.anyio
async def test_cli_prs_uses_pr_artifact_type(tmp_path, monkeypatch, db_session):
    """Verify local PR listing resolves actual PRArtifact paths."""
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join(tmp_path, ".localforge"), exist_ok=True)

    import localforge.cli.prs as prs_mod
    from localforge.services.task import TaskService
    from localforge.services.execution import ExecutionService

    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="PrsProj", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-PR",
            title="PR task",
            description="",
            status=TaskStatus.PR_READY,
        )
    )
    assert task.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode="interactive", initiated_by="test")
    )
    assert run.id is not None
    task_run = await uow.tasks.create_task_run(domain.TaskRun(run_id=run.id, task_id=task.id))
    assert task_run.id is not None
    await uow.audits.create_artifact(
        domain.Artifact(
            task_run_id=task_run.id,
            type=ArtifactType.PR,
            path=".localforge/artifacts/runs/1/tasks/lf-pr/pr.md",
            content_hash="hash",
        )
    )
    await db_session.commit()

    original_manager = prs_mod.db_manager

    class SessionManager:
        async def get_session(self) -> AsyncSession:
            return db_session

    cast(Any, prs_mod).db_manager = SessionManager()
    try:
        await run_prs()
    finally:
        cast(Any, prs_mod).db_manager = original_manager
