import pytest

from localforge.models import domain
from localforge.models.enums import LeaseReleaseReason, WorktreeAttemptStatus
from localforge.services.path_lease import is_path_overlapping
from localforge.storage import UnitOfWork


def test_path_overlap_detection() -> None:
    """Test V6-501: Exact, parent/child, and non-overlapping PathIntent cases."""
    # Exact match
    assert is_path_overlapping("backend/localforge/api", "backend/localforge/api") is True

    # Parent/Child hierarchy overlap
    assert is_path_overlapping("backend/localforge", "backend/localforge/api/app.py") is True
    assert is_path_overlapping("backend/localforge/api/app.py", "backend/localforge") is True

    # Non-overlapping sibling paths
    assert is_path_overlapping("backend/localforge/api", "backend/localforge/cli") is False
    assert is_path_overlapping("src/components/Sidebar.tsx", "src/utils/math.ts") is False


@pytest.mark.asyncio
async def test_path_lease_acquisition_and_conflict(db_manager) -> None:
    """Test V6-501: Lease acquisition and conflict rejection when overlapping paths are claimed by different owners."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.path_leases is not None

        proj = domain.Project(name="Lease Test", root_path="E:/tmp/lease_test", default_branch="main")
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task_1 = await uow.tasks.create_task(domain.Task(project_id=project.id, key="T1", title="Task 1", description="Desc 1"))
        assert task_1.id is not None
        task_run_1 = await uow.tasks.create_task_run(domain.TaskRun(task_id=task_1.id, run_id=1))
        assert task_run_1.id is not None

        task_2 = await uow.tasks.create_task(domain.Task(project_id=project.id, key="T2", title="Task 2", description="Desc 2"))
        assert task_2.id is not None
        task_run_2 = await uow.tasks.create_task_run(domain.TaskRun(task_id=task_2.id, run_id=1))
        assert task_run_2.id is not None



        # Owner 1 acquires lease on backend/localforge
        lease1, conflict_owner, msg1 = await uow.path_leases.acquire_lease(
            project_id=project.id,
            task_run_id=task_run_1.id,
            owner_id="agent_owner_1",
            target_path="backend/localforge",
            is_directory=True,
        )
        assert lease1 is not None
        assert conflict_owner is None

        # Owner 2 attempts to acquire lease on child path backend/localforge/api/app.py -> CONFLICT
        lease2, conflict_owner_2, msg2 = await uow.path_leases.acquire_lease(
            project_id=project.id,
            task_run_id=task_run_2.id,
            owner_id="agent_owner_2",
            target_path="backend/localforge/api/app.py",
        )
        assert lease2 is None
        assert conflict_owner_2 == "agent_owner_1"
        assert "PathIntent conflict" in msg2

        # Owner 1 releases lease
        released = await uow.path_leases.release_all_leases_for_run(task_run_1.id, LeaseReleaseReason.COMPLETED)
        assert released == 1

        # Now Owner 2 can acquire lease
        lease2_retry, conflict_owner_retry, _ = await uow.path_leases.acquire_lease(
            project_id=project.id,
            task_run_id=task_run_2.id,
            owner_id="agent_owner_2",
            target_path="backend/localforge/api/app.py",
        )
        assert lease2_retry is not None
        assert conflict_owner_retry is None


@pytest.mark.asyncio
async def test_worktree_attempt_manifest_and_reconciliation(db_manager, tmp_path) -> None:
    """Test V6-500 & V6-503: Manifest tracking and restart reconciliation."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.worktrees is not None

        proj = domain.Project(name="Worktree Test", root_path=str(tmp_path), default_branch="main")
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = await uow.tasks.create_task(domain.Task(project_id=project.id, key="WT-1", title="Worktree task", description="WT desc"))
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None


        # Create physical directory for active worktree
        wt_dir = tmp_path / "wt_attempt_1"
        wt_dir.mkdir()

        # Create attempt manifest for active worktree
        manifest = await uow.worktrees.create_attempt_manifest(
            project_id=project.id,
            task_id=task.id,
            task_run_id=task_run.id,
            worktree_path=str(wt_dir),
            branch_name="feature/wt-1",
            source_commit="abc1234",
            owner_agent_id="agent_wt_01",
            expected_paths=["src/app.ts"],
        )
        assert manifest.id is not None
        assert manifest.status == WorktreeAttemptStatus.ACTIVE

        # Create non-existent path manifest
        ghost_dir = tmp_path / "wt_ghost_attempt"
        manifest_ghost = await uow.worktrees.create_attempt_manifest(
            project_id=project.id,
            task_id=task.id,
            task_run_id=task_run.id,
            worktree_path=str(ghost_dir),
            branch_name="feature/wt-ghost",
            source_commit="abc1234",
            owner_agent_id="agent_wt_02",
        )

        # Run reconciliation -> Ghost manifest marked STALE, active manifest stays ACTIVE
        res = await uow.worktrees.reconcile_worktree_manifests(project.id)
        assert res["total_manifests"] == 2
        assert res["active_worktrees"] == 1
        assert res["reconciled_stale"] == 1
        assert str(ghost_dir) in res["stale_paths"]
