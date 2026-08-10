import asyncio
import os

import pytest
from localforge.gitops import WorktreeManager
from localforge.models import domain
from localforge.models.enums import (
    ArtifactType,
    AuditEventActorType,
    AuditEventType,
    TaskStatus,
    WorktreeAttemptStatus,
)
from localforge.services.audit import AuditService
from localforge.services.project import ProjectService
from localforge.services.task import TaskService
from localforge.services.worktree import WorktreeService
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore, ArtifactStoreError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_artifact_store_atomic_writes(tmp_path, db_session: AsyncSession):
    """Test physical atomic write constraints, directories layout and SHA-256 calculation."""
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)

    store = ArtifactStore(uow)

    project_root = str(tmp_path / "project")
    os.makedirs(project_root)
    project = await uow.projects.create_project(
        domain.Project(name="Artifact project", root_path=project_root, default_branch="main")
    )
    task = await uow.tasks.create_task(
        domain.Task(project_id=project.id, key="LF-01", title="Plan", description="")
    )
    task_run = await uow.tasks.create_task_run(
        domain.TaskRun(run_id=10, task_id=task.id, attempt_count=1)
    )

    # 1. Write an allowed artifact
    content = "my plan details"
    saved = await store.write_artifact(
        project_root=project_root,
        task_run_id=task_run.id,
        task_key="LF-01",
        run_id=10,
        filename="plan.md",
        content=content,
        summary="A nice plan summary",
    )

    assert saved.id is not None
    assert saved.type == ArtifactType.PLAN
    assert saved.content_hash == "8b25426feb99000790d08bd535008a35861103dad359cf6c591f5772a5c58f1d"
    assert saved.summary == "A nice plan summary"

    # Verify physical file existence and contents
    expected_path = os.path.join(
        project_root,
        ".localforge",
        "artifacts",
        "runs",
        "10",
        "tasks",
        "lf-01",
        "plan.md",
    )
    assert os.path.exists(expected_path)

    read_val = await store.read_artifact(project_root, 10, "LF-01", "plan.md")
    assert read_val == content

    # 2. Try to write disallowed artifact name
    with pytest.raises(ArtifactStoreError) as exc:
        await store.write_artifact(
            project_root=project_root,
            task_run_id=task_run.id,
            task_key="LF-01",
            run_id=10,
            filename="unsupported.txt",
            content="content",
        )
    assert "Filename 'unsupported.txt' is not in the allowed list" in str(exc.value)


@pytest.mark.anyio
async def test_audit_event_redaction_and_replay(db_session: AsyncSession):
    """Verify automatic payload redaction and chronologically ordered replay metadata export."""
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)

    # Mock environment token
    os.environ["LOCALFORGE_GITHUB_TOKEN"] = "super-secret-token-123"

    proj = await uow.projects.create_project(
        domain.Project(name="TestProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None

    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-02", title="Task2", description="Desc")
    )
    assert task.id is not None

    task_run_data = domain.TaskRun(
        run_id=5,
        task_id=task.id,
        attempt_count=1,
    )
    task_run = await uow.tasks.create_task_run(task_run_data)
    assert task_run.id is not None

    # 1. Create audit events with secret to check redaction
    payload = {"command": "git push --token super-secret-token-123", "risk": "high"}
    event = await uow.audits.append_audit_event(
        domain.AuditEvent(
            project_id=proj.id,
            run_id=5,
            task_id=task.id,
            actor_type=AuditEventActorType.AGENT,
            event_type=AuditEventType.STATE_CHANGE,
            payload_redacted=payload,
        )
    )
    assert event.id is not None
    # Payload redacted is automatically sanitized in append_audit_event
    assert "super-secret-token-123" not in event.payload_redacted["command"]
    assert "[REDACTED]" in event.payload_redacted["command"]

    # 2. Add an artifact associated with task
    await uow.audits.create_artifact(
        domain.Artifact(
            task_run_id=task_run.id,
            type=ArtifactType.PLAN,
            path="plan.md",
            content_hash="abc",
            summary="plan sum",
        )
    )

    # 3. Export run replay timeline
    timeline = await uow.audits.export_run_replay(proj.id, 5)
    assert len(timeline) == 1
    event_data = timeline[0]
    assert event_data["id"] == event.id
    assert event_data["event_type"] == "state_change"
    assert "[REDACTED]" in event_data["payload"]["command"]
    # Artifact list should contain our artifact
    assert len(event_data["artifacts"]) == 1
    assert event_data["artifacts"][0]["path"] == "plan.md"


@pytest.mark.anyio
async def test_worktree_concurrency_locks(tmp_path, db_session: AsyncSession):
    """Verify that multiple concurrent operations on the same worktree path serialize correctly."""
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)

    # Clean locks to prevent crossover issues from other tests
    WorktreeManager._locks.clear()

    proj = await uow.projects.create_project(
        domain.Project(name="LockProj", root_path=str(tmp_path), default_branch="main")
    )
    assert proj.id is not None

    manager = WorktreeManager(project_id=proj.id, uow=uow)

    path = str(tmp_path / "worktree")

    lock = manager._get_worktree_lock(path)

    order = []

    async def first_task():
        async with lock:
            order.append("first_entered")
            await asyncio.sleep(0.1)
            order.append("first_exited")

    async def second_task():
        # Will wait for the lock to release
        async with manager._get_worktree_lock(path):
            order.append("second_entered")

    await asyncio.gather(first_task(), second_task())
    assert order == ["first_entered", "first_exited", "second_entered"]


@pytest.mark.anyio
async def test_orphan_worktrees_cleanup(tmp_path, db_session: AsyncSession):
    """Verify scanning and removal of physical worktree directories
    that do not belong to active tasks.
    """
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.worktrees = WorktreeService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="CleanupProj", root_path=str(tmp_path), default_branch="main")
    )
    assert proj.id is not None

    # Setup directories structure
    worktree_base = tmp_path / ".localforge" / "worktrees"
    worktree_base.mkdir(parents=True, exist_ok=True)

    # Active task directory
    active_dir = worktree_base / "lf-10"
    active_dir.mkdir()

    # Orphan directory (completed/done task in database)
    orphan_dir = worktree_base / "lf-11"
    orphan_dir.mkdir()
    user_owned_dir = worktree_base / "manual-debug-copy"
    user_owned_dir.mkdir()

    # Create tasks: LF-10 is active (IMPLEMENTING), LF-11 is final (DONE)
    await uow.tasks.create_task(
        domain.Task(
            project_id=proj.id,
            key="LF-10",
            title="Active Task",
            description="",
            status=TaskStatus.IMPLEMENTING,
        )
    )
    done_task = await uow.tasks.create_task(
        domain.Task(
            project_id=proj.id,
            key="LF-11",
            title="Done Task",
            description="",
            status=TaskStatus.DONE,
        )
    )
    assert done_task.id is not None
    done_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=done_task.id, run_id=1))
    assert done_run.id is not None
    assert uow.worktrees is not None
    await uow.worktrees.create_attempt_manifest(
        project_id=proj.id,
        task_id=done_task.id,
        task_run_id=done_run.id,
        worktree_path=str(orphan_dir),
        branch_name="localforge/lf-11-done-task",
        source_commit="abc1234",
        owner_agent_id="agent-cleanup",
    )
    await uow.session.commit()

    manager = WorktreeManager(project_id=proj.id, uow=uow)
    cleaned = await manager.cleanup_orphan_worktrees()

    # Should only clean the orphan one (lf-11)
    assert len(cleaned) == 1
    assert os.path.basename(cleaned[0]) == "lf-11"
    assert not orphan_dir.exists()
    assert active_dir.exists()
    assert user_owned_dir.exists()


@pytest.mark.anyio
async def test_failed_safe_worktree_is_retained_for_diagnostics(
    tmp_path, db_session: AsyncSession
):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.worktrees = WorktreeService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="RetainFailed", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-12",
            title="Failed task",
            description="",
            status=TaskStatus.FAILED_SAFE,
        )
    )
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
    assert task_run.id is not None

    worktree_dir = tmp_path / ".localforge" / "worktrees" / "lf-12"
    worktree_dir.mkdir(parents=True)
    assert uow.worktrees is not None
    manifest = await uow.worktrees.create_attempt_manifest(
        project_id=project.id,
        task_id=task.id,
        task_run_id=task_run.id,
        worktree_path=str(worktree_dir),
        branch_name="localforge/lf-12-failed-task",
        source_commit="abc1234",
        owner_agent_id="agent-retain",
    )
    assert manifest.id is not None
    await uow.session.commit()

    manager = WorktreeManager(project_id=project.id, uow=uow)
    await manager.cleanup_worktree(task.id)

    assert worktree_dir.exists()
    retained = await uow.worktrees.get_manifest_by_task_run(task_run.id)
    assert retained is not None
    assert retained.status == WorktreeAttemptStatus.REJECTED
