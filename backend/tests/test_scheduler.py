import asyncio
import os

import pytest
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    ArtifactType,
    AuditEventActorType,
    AuditEventType,
    HandoffKind,
    RunMode,
    RunnerHealthState,
    RunStatus,
    TaskRunStatus,
    TaskStatus,
)
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.runners import BaseTaskRunner, RunnerContext, TaskRunnerPool
from localforge.services.scheduler import Scheduler
from localforge.services.task import TaskService
from localforge.services.worktree import WorktreeService
from localforge.storage import UnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession


class FakeRunner(BaseTaskRunner):
    def __init__(self) -> None:
        self.setup_task_ids: list[int] = []

    async def setup(self, task: domain.Task, *, run_id: int, uow) -> RunnerContext:
        assert task.id is not None
        self.setup_task_ids.append(task.id)
        return RunnerContext(
            worktree_path=f"/tmp/localforge/{task.key.lower()}",
            branch_name=f"localforge/{task.key.lower()}",
            source_commit="fake-source-commit",
            sandbox_id="fake-local",
        )

    async def execute(self, task_run: domain.TaskRun, *, uow) -> None:
        pass

    async def checkpoint(self, task_run: domain.TaskRun, name: str, *, uow) -> str:
        return f"checkpoint-{name}"

    async def cleanup(self, task_run: domain.TaskRun, *, uow) -> None:
        pass


def test_scheduler_trigger_wakes_event_wait_without_polling_delay():
    scheduler = Scheduler(project_id=1, run_id=1, loop_interval=60.0)

    async def wait_and_trigger() -> bool:
        waiter = asyncio.create_task(scheduler._wait_for_trigger())
        await asyncio.sleep(0)
        scheduler.trigger()
        return await asyncio.wait_for(waiter, timeout=0.1)

    assert asyncio.run(wait_and_trigger()) is True


@pytest.mark.anyio
async def test_task_status_transition_auditing(db_manager, db_session: AsyncSession):
    """Verify that every task status transition generates a persisted AuditEvent."""
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.worktrees = WorktreeService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="TransitionProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-10", title="Task", description="")
    )
    assert task.id is not None

    # Transition: BACKLOG -> READY
    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
    await uow.session.commit()

    events = await uow.audits.list_audit_events_for_project(proj.id)
    assert len(events) == 1
    assert events[0].event_type == AuditEventType.STATE_CHANGE
    assert events[0].payload_redacted["task_key"] == "LF-10"
    assert events[0].payload_redacted["from_status"] == "BACKLOG"
    assert events[0].payload_redacted["to_status"] == "READY"


@pytest.mark.anyio
async def test_dependency_resolution_blocks_task(db_manager, db_session: AsyncSession):
    """Assert that a task with blocked/failed dependencies is blocked."""
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="DepProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None

    # Task A (Dependency)
    task_a = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-20", title="DepA", description="")
    )
    assert task_a.id is not None

    # Task B (Dependent)
    task_b = await uow.tasks.create_task(
        domain.Task(
            project_id=proj.id,
            key="LF-21",
            title="DependentB",
            description="",
            dependency_task_ids=[task_a.id],
        )
    )
    assert task_b.id is not None

    tasks = [task_a, task_b]

    # Task A is BACKLOG -> not resolved -> Task B not runnable
    assert not await uow.tasks.is_task_runnable(task_b.id, tasks)

    # Move Task A to READY -> not resolved -> Task B not runnable
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.READY)
    assert task_a.id is not None
    tasks = [task_a, task_b]
    assert not await uow.tasks.is_task_runnable(task_b.id, tasks)

    # Move Task A through active statuses to FAILED_SAFE
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.CLAIMED)
    assert task_a.id is not None
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.PLANNING)
    assert task_a.id is not None
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.IMPLEMENTING)
    assert task_a.id is not None
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.TESTING)
    assert task_a.id is not None
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.REPAIRING)
    assert task_a.id is not None
    task_a = await uow.tasks.update_task_status(task_a.id, TaskStatus.FAILED_SAFE)
    assert task_a.id is not None
    tasks = [task_a, task_b]
    assert not await uow.tasks.is_task_runnable(task_b.id, tasks)

    # Check Task B status is updated to BLOCKED
    refreshed_b = await uow.tasks.get_task(task_b.id)
    assert refreshed_b is not None
    assert refreshed_b.status == TaskStatus.BLOCKED


@pytest.mark.anyio
async def test_scrum_master_records_blocker_and_reopens_for_chief(
    db_manager, db_session: AsyncSession
):
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="Scrum", root_path="/p", default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.UNATTENDED, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-30",
            title="Blocked task",
            description="",
            metadata={"task_contract": {"seniority_class": "chief_led"}},
        )
    )
    assert task.id is not None
    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
    await uow.tasks.update_task_status(task.id, TaskStatus.CLAIMED)
    await uow.tasks.update_task_status(task.id, TaskStatus.PLANNING)
    await uow.tasks.update_task_status(task.id, TaskStatus.IMPLEMENTING)
    await uow.tasks.update_task_status(task.id, TaskStatus.FAILED_SAFE)
    await uow.tasks.create_task_run(
        domain.TaskRun(
            run_id=run.id,
            task_id=task.id,
            status=TaskRunStatus.FAILED,
            final_summary="Pipeline execution failed: JSONDecodeError('bad')",
        )
    )

    scheduler = Scheduler(project_id=project.id, run_id=run.id, db_manager=db_manager)
    failed_task = await uow.tasks.get_task(task.id)
    assert failed_task is not None
    await scheduler._scrum_master_record_conformity(uow, [failed_task])
    failed_task = await uow.tasks.get_task(task.id)
    assert failed_task is not None
    reopened = await scheduler._scrum_master_unblock_failed_tasks(uow, [failed_task])

    refreshed = await uow.tasks.get_task(task.id)
    assert reopened == 1
    assert refreshed is not None
    assert refreshed.status == TaskStatus.READY
    assert refreshed.metadata["scrum_master_conformity"]["status"] == "blocked"
    assert refreshed.metadata["task_contract"]["seniority_class"] == "chief_only"
    assert refreshed.metadata["task_contract"]["chief_engineer_unblock_required"] is True


@pytest.mark.anyio
async def test_scrum_master_does_not_reopen_permanent_provider_blocker(
    db_manager, db_session: AsyncSession
):
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="Provider blocker", root_path="/p", default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.UNATTENDED, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-31",
            title="Paid provider task",
            description="",
            metadata={"task_contract": {"seniority_class": "chief_only"}},
        )
    )
    assert task.id is not None
    for status in (
        TaskStatus.READY,
        TaskStatus.CLAIMED,
        TaskStatus.PLANNING,
        TaskStatus.IMPLEMENTING,
        TaskStatus.FAILED_SAFE,
    ):
        await uow.tasks.update_task_status(task.id, status)
    await uow.tasks.create_task_run(
        domain.TaskRun(
            run_id=run.id,
            task_id=task.id,
            status=TaskRunStatus.FAILED,
            final_summary=(
                "Chief Engineer provider is unavailable and requires operator action: "
                "OpenRouter completion failed (402): Insufficient credits"
            ),
        )
    )

    scheduler = Scheduler(project_id=project.id, run_id=run.id, db_manager=db_manager)
    failed_task = await uow.tasks.get_task(task.id)
    assert failed_task is not None
    reopened = await scheduler._scrum_master_unblock_failed_tasks(uow, [failed_task])

    refreshed = await uow.tasks.get_task(task.id)
    assert reopened == 0
    assert refreshed is not None
    assert refreshed.status == TaskStatus.FAILED_SAFE


@pytest.mark.anyio
async def test_replay_pagination(db_manager, db_session: AsyncSession):
    """Verify that export_run_replay correctly supports limit and offset pagination parameters."""
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.audits = AuditService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="PaginationProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None

    # Append 3 events
    for i in range(3):
        await uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=proj.id,
                run_id=100,
                actor_type=AuditEventActorType.SYSTEM,
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={"count": i},
            )
        )
    await uow.session.commit()

    # Replay with limit=2, offset=0 -> returns first 2 events
    page1 = await uow.audits.export_run_replay(proj.id, 100, limit=2, offset=0)
    assert len(page1) == 2
    assert page1[0]["payload"]["count"] == 0
    assert page1[1]["payload"]["count"] == 1

    # Replay with limit=2, offset=2 -> returns remaining 1 event
    page2 = await uow.audits.export_run_replay(proj.id, 100, limit=2, offset=2)
    assert len(page2) == 1
    assert page2[0]["payload"]["count"] == 2


@pytest.mark.anyio
async def test_scheduler_uses_runner_pool_to_prepare_task_execution(
    db_manager, db_session: AsyncSession
):
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.executions = ExecutionService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="RunnerProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-40", title="Runner task", description="")
    )
    assert task.id is not None
    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
    await uow.session.commit()

    runner = FakeRunner()
    scheduler = Scheduler(
        project_id=proj.id,
        run_id=run.id,
        max_parallel_tasks=1,
        db_manager=db_manager,
        runner_pool=TaskRunnerPool([runner]),
    )

    await scheduler._process_iteration()

    refreshed = await uow.tasks.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.PLANNING
    assert runner.setup_task_ids == [task.id]
    task_runs = await uow.tasks.list_runs_for_task(task.id)
    assert task_runs[0].worktree_path == "/tmp/localforge/lf-40"
    assert task_runs[0].branch_name == "localforge/lf-40"
    assert task_runs[0].sandbox_id == "fake-local"
    assert task_runs[0].id is not None

    async with UnitOfWork(db_manager) as verify_uow:
        assert verify_uow.runner_pool is not None
        assert verify_uow.worktrees is not None
        logs = await verify_uow.runner_pool.list_dispatch_logs_for_task_run(task_runs[0].id)
        assert len(logs) == 1
        assert logs[0].dispatch_status == "SUCCESS"
        assert logs[0].selected_runner_id == "scheduler-local-worktree"
        manifest = await verify_uow.worktrees.get_manifest_by_task_run(task_runs[0].id)
        assert manifest is not None
        assert manifest.worktree_path == "/tmp/localforge/lf-40"
        assert manifest.branch_name == "localforge/lf-40"
        assert manifest.source_commit == "fake-source-commit"
        assert manifest.owner_agent_id == "scheduler-local-worktree"


@pytest.mark.anyio
async def test_scheduler_marks_pipeline_failure_failed_safe_and_recovers_session(
    db_manager, db_session: AsyncSession, monkeypatch
):
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="PipelineFailureProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.UNATTENDED, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-41", title="Pipeline task", description="")
    )
    assert task.id is not None
    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
    await uow.session.commit()

    async def fail_pipeline(self, **kwargs):
        raise RuntimeError("pipeline failed")

    monkeypatch.setattr(
        "localforge.services.scheduler.RolePipelineEngine.run_task",
        fail_pipeline,
    )

    scheduler = Scheduler(
        project_id=proj.id,
        run_id=run.id,
        max_parallel_tasks=1,
        db_manager=db_manager,
        runner_pool=TaskRunnerPool([FakeRunner()]),
        execute_pipeline=True,
    )

    await scheduler._process_iteration()

    refreshed = await uow.tasks.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.FAILED_SAFE
    task_runs = await uow.tasks.list_runs_for_task(task.id)
    assert task_runs[0].status.value == "FAILED"
    assert "pipeline failed" in (task_runs[0].final_summary or "")


@pytest.mark.anyio
async def test_scheduler_releases_runner_lease_after_pipeline_success(
    db_manager, db_session: AsyncSession, monkeypatch
):
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="PipelineSuccessProj", root_path="/p", default_branch="main")
    )
    assert proj.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.UNATTENDED, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-42", title="Pipeline task", description="")
    )
    assert task.id is not None
    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
    await uow.session.commit()

    async def pass_pipeline(self, *, task_id: int, task_run_id: int, **kwargs) -> None:
        assert self.uow.tasks is not None
        await self.uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)
        await self.uow.tasks.update_task_status(task_id, TaskStatus.TESTING)
        await self.uow.tasks.update_task_status(task_id, TaskStatus.REVIEWING)
        task_run = await self.uow.tasks.get_task_run(task_run_id)
        assert task_run is not None
        assert self.uow.audits is not None
        artifact = await self.uow.audits.create_artifact(
            domain.Artifact(
                task_run_id=task_run_id,
                type=ArtifactType.PR,
                path=f".localforge/artifacts/runs/{task_run.run_id}/tasks/lf-42/pr.md",
                content_hash="a" * 64,
            )
        )
        assert self.uow.executions is not None
        handoff = await self.uow.executions.create_handoff(
            domain.Handoff(
                task_run_id=task_run_id,
                from_role=AgentRole.REVIEWER,
                to_role=AgentRole.PR_WRITER,
                kind=HandoffKind.PR_READY,
                payload_json={"source": "test_scheduler_pipeline"},
            )
        )
        await self.uow.tasks.mark_pr_ready(
            task_id,
            gate_evidence={
                "source": "test_scheduler_pipeline",
                "task_run_id": task_run_id,
                "handoff_id": handoff.id,
                "maker_id": "scheduler-test",
                "checker_id": "mechanical-pre-pr-gate",
                "maker_attempt_id": f"scheduler-test:{task_run_id}",
                "checker_attempt_id": f"mechanical-pre-pr-gate:{task_run_id}",
                "pre_pr_gate": {
                    "passed": True,
                    "source_commit": "source-commit",
                    "target_commit": "target-commit",
                    "diff_hash": "a" * 64,
                },
                "risk_verdict": {"passed": True, "source": "test_scheduler_pipeline"},
                "safety_verdict": {"passed": True, "source": "test_scheduler_pipeline"},
                "checks_executed": ["pytest"],
                "artifact_paths": [artifact.path],
                "branch_name": task_run.branch_name,
                "worktree_path": task_run.worktree_path,
                "source_commit": "source-commit",
                "target_commit": "target-commit",
                "diff_hash": "a" * 64,
            },
        )
        task_run.status = TaskRunStatus.COMPLETED
        await self.uow.tasks.update_task_run(task_run)

    monkeypatch.setattr(
        "localforge.services.scheduler.RolePipelineEngine.run_task",
        pass_pipeline,
    )

    scheduler = Scheduler(
        project_id=proj.id,
        run_id=run.id,
        max_parallel_tasks=1,
        db_manager=db_manager,
        runner_pool=TaskRunnerPool([FakeRunner()]),
        execute_pipeline=True,
    )

    await scheduler._process_iteration()

    async with UnitOfWork(db_manager) as verify_uow:
        assert verify_uow.runner_pool is not None
        runners = await verify_uow.runner_pool.list_runners()
        runner = next(r for r in runners if r.runner_id == "scheduler-local-worktree")
        assert runner.active_tasks_count == 0
        assert runner.health_state == RunnerHealthState.READY


@pytest.mark.anyio
async def test_scheduler_lifecycle_and_parallel_limits(
    tmp_path, db_manager, db_session: AsyncSession
):
    """Verify scheduler loop claiming tasks, creating TaskRuns, and running cleanups."""
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.worktrees = WorktreeService(db_session)

    # 1. Setup project
    proj = await uow.projects.create_project(
        domain.Project(name="SchProj", root_path=str(tmp_path), default_branch="main")
    )
    assert proj.id is not None

    # Initial commit to create main branch and HEAD in temp repository
    import git

    repo = git.Repo.init(str(tmp_path))
    readme = tmp_path / "README.md"
    readme.write_text("# Test Repo")
    repo.index.add([str(readme)])
    repo.index.commit("initial commit")
    try:
        repo.git.branch("-M", "main")
    except Exception:
        pass

    # 2. Setup run
    run = await uow.executions.create_run(
        domain.Run(
            project_id=proj.id,
            mode=RunMode.INTERACTIVE,
            initiated_by="test-agent",
            status=RunStatus.PENDING,
        )
    )
    assert run.id is not None

    # 3. Setup tasks
    task1 = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-30", title="Task 1", description="")
    )
    assert task1.id is not None
    task2 = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-31", title="Task 2", description="")
    )
    assert task2.id is not None
    task3 = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-32", title="Task 3", description="")
    )
    assert task3.id is not None

    # Move them to READY
    await uow.tasks.update_task_status(task1.id, TaskStatus.READY)
    await uow.tasks.update_task_status(task2.id, TaskStatus.READY)
    await uow.tasks.update_task_status(task3.id, TaskStatus.READY)
    await uow.session.commit()

    # 4. Instantiate scheduler with max_parallel_tasks=2
    scheduler = Scheduler(
        project_id=proj.id,
        run_id=run.id,
        max_parallel_tasks=2,
        db_manager=db_manager,
    )

    # Run one single processing iteration of the scheduler
    # Using private method to test deterministically without launching asyncio background loop
    await scheduler._process_iteration()
    await uow.session.commit()

    # Refreshed states
    run_ref = await uow.executions.get_run(run.id)
    assert run_ref is not None
    assert run_ref.status == RunStatus.RUNNING

    t1_ref = await uow.tasks.get_task(task1.id)
    t2_ref = await uow.tasks.get_task(task2.id)
    t3_ref = await uow.tasks.get_task(task3.id)
    assert t1_ref is not None
    assert t2_ref is not None
    assert t3_ref is not None

    # Exactly 2 tasks should have been claimed and moved to PLANNING (due to max_parallel_tasks=2)
    planning_count = 0
    ready_count = 0
    for t in (t1_ref, t2_ref, t3_ref):
        if t.status == TaskStatus.PLANNING:
            planning_count += 1
        elif t.status == TaskStatus.READY:
            ready_count += 1

    assert planning_count == 2
    assert ready_count == 1

    # Verify that TaskRun database records were created for the executing tasks
    claimed_ids: list[int] = []
    for t in (t1_ref, t2_ref):
        if t.status == TaskStatus.PLANNING:
            assert t.id is not None
            claimed_ids.append(t.id)

    for tid in claimed_ids:
        runs = await uow.tasks.list_runs_for_task(tid)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.RUNNING
        assert runs[0].worktree_path is not None
        assert os.path.exists(runs[0].worktree_path)

    # Clean up worktrees physically
    from localforge.gitops.manager import WorktreeManager

    wt_manager = WorktreeManager(project_id=proj.id, uow=uow)
    for tid in claimed_ids:
        runs = await uow.tasks.list_runs_for_task(tid)
        assert runs
        task_run = runs[0]
        # Move task status to final state (DONE) to allow cleanup
        await uow.tasks.update_task_status(tid, TaskStatus.IMPLEMENTING)
        await uow.tasks.update_task_status(tid, TaskStatus.TESTING)
        await uow.tasks.update_task_status(tid, TaskStatus.REVIEWING)
        assert uow.audits is not None
        artifact = await uow.audits.create_artifact(
            domain.Artifact(
                task_run_id=task_run.id or 0,
                type=ArtifactType.PR,
                path=f".localforge/artifacts/runs/{task_run.run_id}/tasks/{tid}/pr.md",
                content_hash="b" * 64,
            )
        )
        assert uow.executions is not None
        handoff = await uow.executions.create_handoff(
            domain.Handoff(
                task_run_id=task_run.id or 0,
                from_role=AgentRole.REVIEWER,
                to_role=AgentRole.PR_WRITER,
                kind=HandoffKind.PR_READY,
                payload_json={"source": "test_scheduler_cleanup"},
            )
        )
        assert uow.worktrees is not None
        manifest = await uow.worktrees.get_manifest_by_task_run(task_run.id or 0)
        assert manifest is not None
        source_commit = manifest.source_commit
        await uow.tasks.mark_pr_ready(
            tid,
            gate_evidence={
                "source": "test_scheduler_cleanup",
                "task_run_id": task_run.id or 0,
                "handoff_id": handoff.id,
                "maker_id": "scheduler-test",
                "checker_id": "mechanical-pre-pr-gate",
                "maker_attempt_id": f"scheduler-test:{task_run.id or 0}",
                "checker_attempt_id": f"mechanical-pre-pr-gate:{task_run.id or 0}",
                "pre_pr_gate": {
                    "passed": True,
                    "source_commit": source_commit,
                    "target_commit": "target-commit",
                    "diff_hash": "b" * 64,
                },
                "risk_verdict": {"passed": True, "source": "test_scheduler_cleanup"},
                "safety_verdict": {"passed": True, "source": "test_scheduler_cleanup"},
                "checks_executed": ["pytest"],
                "artifact_paths": [artifact.path],
                "branch_name": task_run.branch_name,
                "worktree_path": task_run.worktree_path,
                "source_commit": source_commit,
                "target_commit": "target-commit",
                "diff_hash": "b" * 64,
            },
        )
        await uow.tasks.update_task_status(tid, TaskStatus.DONE)
        await uow.session.commit()
        await wt_manager.cleanup_worktree(tid)
