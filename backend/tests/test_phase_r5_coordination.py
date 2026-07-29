from datetime import UTC, datetime, timedelta

import pytest
from localforge.models import domain
from localforge.models.enums import LeaseReleaseReason, RunnerLane
from localforge.services.path_lease import is_path_overlapping, normalize_lease_path
from localforge.storage import UnitOfWork


async def _create_project_task_run(uow: UnitOfWork, *, key: str = "R5-1") -> tuple[int, int, int]:
    assert uow.projects is not None
    assert uow.tasks is not None
    project = await uow.projects.create_project(
        domain.Project(name=f"{key} Project", root_path="E:/tmp/r5", default_branch="main")
    )
    assert project.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=project.id, key=key, title=key, description="R5 coordination")
    )
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(domain.TaskRun(run_id=1, task_id=task.id))
    assert task_run.id is not None
    return project.id, task.id, task_run.id


def test_r5_path_normalization_handles_separators_and_case() -> None:
    assert normalize_lease_path("backend\\localforge\\api\\..\\api/app.py").endswith(
        "backend/localforge/api/app.py"
    )
    assert is_path_overlapping("Backend\\LocalForge", "backend/localforge/api/app.py") is True
    assert is_path_overlapping("backend/localforge/api", "backend/localforge/cli") is False


@pytest.mark.asyncio
async def test_r5_path_lease_fencing_renewal_and_reacquire(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow)

        lease, conflict_owner, _ = await uow.path_leases.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-a",
            target_path="backend/localforge",
            is_directory=True,
            ttl_seconds=60,
            attempt_number=2,
            worktree_path="E:/tmp/r5/.localforge/worktrees/r5-1",
            fencing_token="token-a",
        )
        assert lease is not None
        assert conflict_owner is None
        assert lease.normalized_target_path == normalize_lease_path("backend/localforge")
        assert lease.attempt_number == 2
        assert lease.worktree_path is not None
        assert lease.fencing_token == "token-a"

        renewed = await uow.path_leases.renew_lease(
            lease.id or 0,
            owner_id="agent-a",
            fencing_token="token-a",
            ttl_seconds=120,
        )
        assert renewed is not None
        assert renewed.ttl_seconds == 120

        stale_release = await uow.path_leases.release_lease(
            lease.id or 0,
            LeaseReleaseReason.COMPLETED,
            owner_id="agent-a",
            fencing_token="wrong-token",
        )
        assert stale_release is None
        active = await uow.path_leases.list_active_leases(project_id)
        assert len(active) == 1

        released = await uow.path_leases.release_lease(
            lease.id or 0,
            LeaseReleaseReason.COMPLETED,
            owner_id="agent-a",
            fencing_token="token-a",
        )
        assert released is not None

        reacquired, reacquire_conflict, _ = await uow.path_leases.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="backend/localforge",
            fencing_token="token-b",
        )
        assert reacquired is not None
        assert reacquire_conflict is None
        assert reacquired.fencing_token == "token-b"


@pytest.mark.asyncio
async def test_r5_expired_path_lease_can_be_reclaimed_with_new_fencing(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-2")
        lease, _, _ = await uow.path_leases.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-a",
            target_path="src/board.ts",
            ttl_seconds=1,
            fencing_token="old-token",
        )
        assert lease is not None
        assert lease.id is not None

        from localforge.storage.orm import PathLeaseORM

        orm_lease = await uow.session.get(PathLeaseORM, lease.id)
        assert orm_lease is not None
        orm_lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        orm_lease.active_conflict_key = None
        await uow.session.flush()

        reclaimed, conflict_owner, _ = await uow.path_leases.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/board.ts",
            fencing_token="new-token",
        )
        assert reclaimed is not None
        assert conflict_owner is None
        assert reclaimed.fencing_token == "new-token"


@pytest.mark.asyncio
async def test_r5_runner_stale_fencing_token_cannot_release_newer_reservation(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-3")
        caps = domain.RunnerCapability(lane=RunnerLane.INLINE, max_concurrency=1)
        await uow.runner_pool.register_runner("runner-r5", "Runner R5", RunnerLane.INLINE, caps, 1)

        runner, status, first_log = await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=task_run_id,
            required_lane=RunnerLane.INLINE,
        )
        assert runner is not None
        assert status == "SUCCESS"
        assert first_log.lease_token is not None

        await uow.runner_pool.release_runner_lease(
            "runner-r5",
            task_run_id=task_run_id,
            lease_token=first_log.lease_token,
        )
        second_runner, second_status, second_log = await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=task_run_id,
            required_lane=RunnerLane.INLINE,
        )
        assert second_runner is not None
        assert second_status == "SUCCESS"
        assert second_log.lease_token is not None

        with pytest.raises(ValueError, match="does not match"):
            await uow.runner_pool.release_runner_lease(
                "runner-r5",
                task_run_id=task_run_id,
                lease_token=first_log.lease_token,
            )

        current = await uow.runner_pool.heartbeat_runner_lease(
            "runner-r5",
            task_run_id=task_run_id,
            lease_token=second_log.lease_token,
        )
        assert current is not None
