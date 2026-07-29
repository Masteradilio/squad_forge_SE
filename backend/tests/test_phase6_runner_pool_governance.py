import pytest
from localforge.models import domain
from localforge.models.enums import RunnerHealthState, RunnerLane, TaskRunStatus
from localforge.storage import UnitOfWork


@pytest.mark.asyncio
async def test_runner_capability_matching_and_no_compatible_runner(db_manager) -> None:
    """Test V6-600 & V6-602: Capability filtering and rejection when no runner satisfies requirements."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.runner_pool is not None

        proj = domain.Project(
            name="Runner Test", root_path="E:/tmp/runner_test", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = await uow.tasks.create_task(
            domain.Task(project_id=project.id, key="RP-1", title="Task 1", description="Desc 1")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        # Register runner 1: INLINE, tools=[git, pytest]
        caps1 = domain.RunnerCapability(
            lane=RunnerLane.INLINE, tools=["git", "pytest"], max_concurrency=2
        )
        await uow.runner_pool.register_runner(
            "runner_inline_1", "Inline 1", RunnerLane.INLINE, caps1, 2
        )

        # Dispatch requesting tool 'docker' -> NO_COMPATIBLE_RUNNER
        runner_none, status_err, log_err = await uow.runner_pool.dispatch_task(
            project_id=project.id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.INLINE,
            required_tools=["docker"],
        )
        assert runner_none is None
        assert status_err == "NO_COMPATIBLE_RUNNER"
        assert "Missing required tools" in log_err.rejection_reasons_json.get("runner_inline_1", "")

        # Dispatch requesting tool 'pytest' -> SUCCESS
        runner_ok, status_ok, _ = await uow.runner_pool.dispatch_task(
            project_id=project.id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.INLINE,
            required_tools=["pytest"],
        )
        assert runner_ok is not None
        assert runner_ok.runner_id == "runner_inline_1"
        assert status_ok == "SUCCESS"


@pytest.mark.asyncio
async def test_quarantined_exclusion_and_stable_ranking(db_manager) -> None:
    """Test V6-601 & V6-602: Quarantined exclusion and stable tie-breaking ranking."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.runner_pool is not None

        proj = domain.Project(
            name="Ranking Test", root_path="E:/tmp/rank_test", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = await uow.tasks.create_task(
            domain.Task(project_id=project.id, key="RP-2", title="Task 2", description="Desc 2")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        # Register 3 runners with identical capabilities
        caps = domain.RunnerCapability(
            lane=RunnerLane.BACKGROUND, tools=["python"], max_concurrency=4
        )
        await uow.runner_pool.register_runner(
            "runner_b", "Runner B", RunnerLane.BACKGROUND, caps, 4
        )
        await uow.runner_pool.register_runner(
            "runner_a", "Runner A", RunnerLane.BACKGROUND, caps, 4
        )
        await uow.runner_pool.register_runner(
            "runner_q", "Runner Q", RunnerLane.BACKGROUND, caps, 4
        )

        # Quarantining runner_a
        await uow.runner_pool.update_runner_health(
            "runner_q", RunnerHealthState.QUARANTINED, "Flaky hardware"
        )

        # Dispatch task -> runner_q is excluded. Between runner_a and runner_b (same score), runner_a wins by stable tie-break (alphabetical id)
        runner_selected, status_str, log = await uow.runner_pool.dispatch_task(
            project_id=project.id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.BACKGROUND,
        )
        assert runner_selected is not None
        assert runner_selected.runner_id == "runner_a"
        assert status_str == "SUCCESS"
        assert "Excluded due to health state" in log.rejection_reasons_json.get("runner_q", "")


@pytest.mark.asyncio
async def test_concurrency_lease_release_and_restart_reconciliation(db_manager) -> None:
    """Test V6-601 & V6-603: Concurrency capacity exhaustion, release, and leaked lease reconciliation."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.runner_pool is not None

        proj = domain.Project(
            name="Lease Test", root_path="E:/tmp/leak_test", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = await uow.tasks.create_task(
            domain.Task(project_id=project.id, key="RP-3", title="Task 3", description="Desc 3")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        # Register runner with max_concurrency=1
        caps = domain.RunnerCapability(lane=RunnerLane.ISOLATED, max_concurrency=1)
        await uow.runner_pool.register_runner("runner_iso_1", "Iso 1", RunnerLane.ISOLATED, caps, 1)

        # 1st dispatch -> succeeds and exhausts capacity
        runner1, status1, first_log = await uow.runner_pool.dispatch_task(
            project_id=project.id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.ISOLATED,
        )
        assert runner1 is not None
        assert runner1.active_tasks_count == 1
        assert runner1.health_state == RunnerHealthState.BUSY

        # 2nd dispatch -> fails due to capacity exhaustion
        runner2, status2, log2 = await uow.runner_pool.dispatch_task(
            project_id=project.id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.ISOLATED,
        )
        assert runner2 is None
        assert status2 == "NO_COMPATIBLE_RUNNER"
        assert "Concurrency capacity exhausted" in log2.rejection_reasons_json.get(
            "runner_iso_1", ""
        )

        # Restart reconciliation preserves capacity for still-active task runs.
        reconciled_count = await uow.runner_pool.reconcile_leaked_leases()
        assert reconciled_count == 0
        still_busy = (await uow.runner_pool.list_runners())[0]
        assert still_busy.active_tasks_count == 1
        assert still_busy.health_state == RunnerHealthState.BUSY

        task_run.status = TaskRunStatus.COMPLETED
        await uow.tasks.update_task_run(task_run)
        assert first_log.lease_token is not None
        await uow.runner_pool.release_runner_lease(
            "runner_iso_1",
            task_run_id=task_run.id,
            lease_token=first_log.lease_token,
        )

        # 3rd dispatch after task completion and fenced release -> succeeds again
        runner3, status3, _ = await uow.runner_pool.dispatch_task(
            project_id=project.id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.ISOLATED,
        )
        assert runner3 is not None
        assert runner3.runner_id == "runner_iso_1"
        assert status3 == "SUCCESS"
