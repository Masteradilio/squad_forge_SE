import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from localforge.models import domain
from localforge.models.enums import (
    LeaseReleaseReason,
    PathLeaseWaitStatus,
    RunnerHealthState,
    RunnerLane,
    TaskRunStatus,
)
from localforge.services.path_lease import (
    canonicalize_repository_relative_path,
    is_path_overlapping,
    normalize_lease_path,
)
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager
from localforge.storage.orm import RunnerPoolStateORM
from sqlalchemy import select


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


def test_r5_repository_boundary_canonicalization_rejects_traversal(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo_root.mkdir()
    outside.mkdir()

    assert (
        canonicalize_repository_relative_path("src/../src/app.py", str(repo_root))
        == "src/app.py"
    )
    with pytest.raises(ValueError, match="outside repository root"):
        canonicalize_repository_relative_path("../outside/app.py", str(repo_root))


def test_r5_repository_boundary_canonicalization_rejects_symlink_escape(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo_root.mkdir()
    outside.mkdir()
    link_path = repo_root / "external"
    try:
        os.symlink(outside, link_path, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")

    with pytest.raises(ValueError, match="outside repository root"):
        canonicalize_repository_relative_path("external/file.py", str(repo_root))


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
async def test_r5_path_lease_acquire_rejects_repository_boundary_escape(db_manager, tmp_path) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-B")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        lease, conflict_owner, message = await uow.path_leases.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-boundary",
            target_path="../outside.py",
            repository_root=str(repo_root),
        )

        assert lease is None
        assert conflict_owner is None
        assert "outside repository root" in message


@pytest.mark.asyncio
async def test_r5_parent_child_path_race_is_serialized_by_database(tmp_path) -> None:
    db_file = tmp_path / "r5-path-race.db"
    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    await bootstrap_database(manager)
    try:
        async with UnitOfWork(manager) as uow:
            project_id, _, first_run_id = await _create_project_task_run(uow, key="R5-RACE-A")
            assert uow.tasks is not None
            task = await uow.tasks.create_task(
                domain.Task(
                    project_id=project_id,
                    key="R5-RACE-B",
                    title="Race B",
                    description="child contender",
                )
            )
            assert task.id is not None
            second_run = await uow.tasks.create_task_run(
                domain.TaskRun(run_id=1, task_id=task.id)
            )
            assert second_run.id is not None
            second_run_id = second_run.id

        async def acquire(owner_id: str, task_run_id: int, target_path: str):
            async with UnitOfWork(manager) as uow:
                assert uow.path_leases is not None
                return await uow.path_leases.acquire_lease(
                    project_id=project_id,
                    task_run_id=task_run_id,
                    owner_id=owner_id,
                    target_path=target_path,
                    ttl_seconds=60,
                )

        first, second = await asyncio.gather(
            acquire("owner-parent", first_run_id, "src"),
            acquire("owner-child", second_run_id, "src/components/board.ts"),
        )

        leases = [first[0], second[0]]
        conflicts = [first[1], second[1]]
        messages = [first[2], second[2]]
        assert sum(lease is not None for lease in leases) == 1
        assert sum(conflict is not None for conflict in conflicts) == 1
        assert any("overlaps with active lease" in message for message in messages)

        async with UnitOfWork(manager) as uow:
            assert uow.path_leases is not None
            active = await uow.path_leases.list_active_leases(project_id)
            assert len(active) == 1
    finally:
        await manager.close()


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
async def test_r5_path_lease_wait_is_persisted_fifo_and_cancellable(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-W")
        lease, _, _ = await uow.path_leases.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-a",
            target_path="src/board.ts",
            fencing_token="owner-token",
        )
        assert lease is not None

        blocked, wait, msg = await uow.path_leases.acquire_or_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/board.ts",
            wait_timeout_seconds=30,
            fencing_token="waiter-token",
        )

        assert blocked is None
        assert wait is not None
        assert wait.status == PathLeaseWaitStatus.WAITING
        assert wait.blocking_owner_id == "agent-a"
        assert wait.queue_position == 1
        assert "overlaps with active lease" in msg

        waits = await uow.path_leases.list_waits_for_project(
            project_id,
            status=PathLeaseWaitStatus.WAITING,
        )
        assert [queued.owner_id for queued in waits] == ["agent-b"]

        cancelled = await uow.path_leases.cancel_wait(
            wait.id or 0,
            owner_id="agent-b",
            reason="Test cancellation.",
        )
        assert cancelled is not None
        assert cancelled.status == PathLeaseWaitStatus.CANCELLED


@pytest.mark.asyncio
async def test_r5_path_lease_wait_timeout_is_persisted(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-T")
        wait = await uow.path_leases.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/late.ts",
            blocking_owner_id="agent-a",
            timeout_seconds=-1,
        )
        assert wait.status == PathLeaseWaitStatus.WAITING

        expired_count = await uow.path_leases.expire_waits()
        assert expired_count == 1
        waits = await uow.path_leases.list_waits_for_project(project_id)
        assert waits[0].status == PathLeaseWaitStatus.TIMED_OUT
        assert waits[0].resolved_at is not None


@pytest.mark.asyncio
async def test_r5_path_lease_repeated_contention_escalates(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-E")

        first_wait = await uow.path_leases.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/contended.ts",
            blocking_owner_id="agent-a",
            timeout_seconds=60,
            escalation_threshold=3,
        )
        second_wait = await uow.path_leases.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/contended.ts",
            blocking_owner_id="agent-a",
            timeout_seconds=60,
            escalation_threshold=3,
        )
        escalated_wait = await uow.path_leases.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/contended.ts",
            blocking_owner_id="agent-a",
            timeout_seconds=60,
            escalation_threshold=3,
        )

        assert first_wait.status == PathLeaseWaitStatus.WAITING
        assert second_wait.status == PathLeaseWaitStatus.WAITING
        assert escalated_wait.status == PathLeaseWaitStatus.ESCALATED
        assert escalated_wait.contention_count == 3
        assert escalated_wait.escalated_at is not None
        assert "busy-waiting" in (escalated_wait.reason or "")


@pytest.mark.asyncio
async def test_r5_path_lease_deadlock_victim_is_deterministic(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-D")

        first = await uow.path_leases.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-a",
            target_path="src/a.ts",
            blocking_owner_id="agent-b",
            timeout_seconds=60,
        )
        second = await uow.path_leases.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id="agent-b",
            target_path="src/b.ts",
            blocking_owner_id="agent-a",
            timeout_seconds=60,
        )

        assert first.status == PathLeaseWaitStatus.WAITING
        assert second.status == PathLeaseWaitStatus.DEADLOCK_VICTIM
        waits = await uow.path_leases.list_waits_for_project(project_id)
        victim_wait = next(wait for wait in waits if wait.owner_id == "agent-b")
        assert victim_wait.status == PathLeaseWaitStatus.DEADLOCK_VICTIM
        assert "Deadlock detected" in (victim_wait.reason or "")


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


@pytest.mark.asyncio
async def test_r5_runner_restart_reconciles_capacity_from_task_run_truth(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        assert uow.tasks is not None
        assert uow.session is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-4")
        second_task = await uow.tasks.create_task(
            domain.Task(
                project_id=project_id,
                key="R5-4B",
                title="R5 second task",
                description="Completed task should not consume runner capacity",
            )
        )
        assert second_task.id is not None
        completed_task_run = await uow.tasks.create_task_run(
            domain.TaskRun(
                run_id=1,
                task_id=second_task.id,
                status=TaskRunStatus.COMPLETED,
                ended_at=datetime.now(UTC),
            )
        )
        assert completed_task_run.id is not None

        caps = domain.RunnerCapability(lane=RunnerLane.INLINE, max_concurrency=2)
        await uow.runner_pool.register_runner(
            "runner-reconcile", "Runner Reconcile", RunnerLane.INLINE, caps, 2
        )
        await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=task_run_id,
            required_lane=RunnerLane.INLINE,
        )
        await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=completed_task_run.id,
            required_lane=RunnerLane.INLINE,
        )

        result = await uow.session.execute(
            select(RunnerPoolStateORM).where(RunnerPoolStateORM.runner_id == "runner-reconcile")
        )
        runner_orm = result.scalar_one_or_none()
        assert runner_orm is not None
        runner_orm.active_tasks_count = 0
        runner_orm.health_state = RunnerHealthState.READY.value
        await uow.session.flush()

        changed = await uow.runner_pool.reconcile_leaked_leases()
        runner_state = (await uow.runner_pool.list_runners())[0]

        assert changed == 1
        assert runner_state.active_tasks_count == 1
        assert runner_state.health_state == RunnerHealthState.READY


@pytest.mark.asyncio
async def test_r5_runner_backpressure_is_bounded_and_fifo_reported(db_manager) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        project_id, _, task_run_id = await _create_project_task_run(uow, key="R5-5")
        caps = domain.RunnerCapability(lane=RunnerLane.INLINE, max_concurrency=1)
        await uow.runner_pool.register_runner(
            "runner-backpressure", "Runner Backpressure", RunnerLane.INLINE, caps, 1
        )
        await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=task_run_id,
            required_lane=RunnerLane.INLINE,
        )

        first_waiter, first_status, first_log = await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=task_run_id,
            required_lane=RunnerLane.INLINE,
            backpressure_queue_limit=1,
        )
        assert first_waiter is None
        assert first_status == "BACKPRESSURE_LIMITED"
        assert "queue_position=1" in first_log.rejection_reasons_json.get("_backpressure", "")

        second_waiter, second_status, second_log = await uow.runner_pool.dispatch_task(
            project_id=project_id,
            task_run_id=task_run_id,
            required_lane=RunnerLane.INLINE,
            backpressure_queue_limit=1,
        )
        assert second_waiter is None
        assert second_status == "BACKPRESSURE_QUEUE_FULL"
        assert "limit reached" in second_log.rejection_reasons_json.get("_backpressure", "")
