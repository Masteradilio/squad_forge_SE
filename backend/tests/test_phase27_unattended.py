from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from localforge.core.config import load_config
from localforge.llm.context import (
    get_llm_call_count,
    reset_llm_call_counter,
    set_active_task_run_id,
    set_llm_limit,
)
from localforge.llm.openai_compatible import OpenAICompatibleProvider
from localforge.models import domain
from localforge.models.enums import (
    AuditEventActorType,
    AuditEventType,
    RunStatus,
    TaskRunStatus,
    TaskStatus,
)
from localforge.runtime.file_tools import SafeFileEditor
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.runners import BaseTaskRunner, RunnerContext, TaskRunnerPool
from localforge.services.scheduler import Scheduler
from localforge.services.task import TaskService
from localforge.storage import UnitOfWork


class StubRunner(BaseTaskRunner):
    def __init__(self, worktree_path: str):
        self.worktree_path = worktree_path

    async def setup(self, task: domain.Task, *, run_id: int, uow: Any) -> RunnerContext:
        return RunnerContext(
            worktree_path=self.worktree_path,
            branch_name=f"localforge/{task.key.lower()}",
            sandbox_id="stub",
        )

    async def execute(self, task_run: domain.TaskRun, *, uow: Any) -> None:
        return None

    async def checkpoint(self, task_run: domain.TaskRun, name: str, *, uow: Any) -> str:
        return name

    async def cleanup(self, task_run: domain.TaskRun, *, uow: Any) -> None:
        return None


async def transition_task_to(uow: UnitOfWork, task_id: int, target_status: TaskStatus) -> None:
    """Helper to transition tasks sequentially satisfying status rules."""
    assert uow.tasks is not None
    ladder = [
        TaskStatus.BACKLOG,
        TaskStatus.READY,
        TaskStatus.CLAIMED,
        TaskStatus.PLANNING,
        TaskStatus.IMPLEMENTING,
        TaskStatus.TESTING,
        TaskStatus.REVIEWING,
        TaskStatus.PR_READY,
        TaskStatus.DONE,
    ]

    if target_status in (TaskStatus.BLOCKED, TaskStatus.FAILED_SAFE, TaskStatus.CANCELLED):
        # Route to IMPLEMENTING then final state
        for status in ladder[1:5]:  # READY, CLAIMED, PLANNING, IMPLEMENTING
            await uow.tasks.update_task_status(task_id, status)
        await uow.tasks.update_task_status(task_id, target_status)
        return

    current_task = await uow.tasks.get_task(task_id)
    assert current_task is not None
    current_status = current_task.status
    current_index = ladder.index(current_status) if current_status in ladder else 0
    target_index = ladder.index(target_status)

    for status in ladder[current_index + 1 : target_index + 1]:
        await uow.tasks.update_task_status(task_id, status)


def test_budgets_default_config():
    """Verify that core default configurations include the baseline resource budgets."""
    config = load_config()
    assert config.budgets is not None
    assert config.budgets.max_run_time == 5400.0
    assert config.budgets.max_task_duration == 900.0
    assert config.budgets.max_repair_attempts == 5
    assert config.budgets.max_parallel_tasks == 2
    assert config.budgets.max_active_model_calls == 4
    assert config.budgets.max_diff_growth == 4000
    assert config.budgets.max_file_count == 12
    assert config.budgets.max_repair_attempts_absolute == 10
    assert config.budgets.max_run_recovery_cycles == 3
    assert config.budgets.max_paid_usd_absolute == 6.0


@pytest.mark.anyio
async def test_llm_call_budget_enforcement():
    """Verify that chat completions check and raise errors
    if active model calls budget is exceeded.
    """
    set_active_task_run_id(999)
    reset_llm_call_counter(999)
    set_llm_limit(999, 2)

    # Initialize with default_model to satisfy openai_compatible validation
    provider = OpenAICompatibleProvider(base_url="http://mock-url", default_model="mock-model")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "response_content"}}]}

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        # Call 1: Success
        res1 = await provider.chat_completion([{"role": "user", "content": "hi"}])
        assert res1 == "response_content"
        assert get_llm_call_count(999) == 1

        # Call 2: Success
        res2 = await provider.chat_completion([{"role": "user", "content": "hi"}])
        assert res2 == "response_content"
        assert get_llm_call_count(999) == 2

        # Call 3: Exceeds limit
        with pytest.raises(ValueError) as exc:
            await provider.chat_completion([{"role": "user", "content": "hi"}])
        assert "exceeded maximum LLM call budget" in str(exc.value)

    set_active_task_run_id(None)


@pytest.mark.anyio
async def test_workspace_file_and_diff_limits(tmp_path, db_session):
    """Verify that workspace changes (files count, diff size) are validated
    and restricted during edits.
    """
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    from localforge.services.audit import AuditService

    uow.audits = AuditService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="BudgetProj", root_path=str(tmp_path), default_branch="main")
    )
    run = await uow.executions.create_run(
        domain.Run(project_id=proj.id, mode="interactive", initiated_by="test")
    )

    editor = SafeFileEditor(uow, project_id=proj.id, run_id=run.id, task_id=1)

    mock_toplevel = MagicMock()
    mock_toplevel.stdout = str(tmp_path) + "\n"

    mock_porcelain = MagicMock()
    mock_porcelain.stdout = " M file1.txt\n M file2.txt\n M file3.txt\n"

    mock_diff = MagicMock()
    mock_diff.stdout = "a" * 1000

    # Setup overrides in resource limits
    run.resource_limits = {"max_file_count": 2, "max_diff_growth": 500}
    await uow.executions.update_run(run)
    await uow.session.commit()

    with (
        patch("subprocess.run") as mock_sub,
        patch(
            "localforge.runtime.file_tools.SafeFileEditor._evaluate",
            return_value=(None, None),
        ),
    ):
        # 1. Simulate file count limit exceeded
        mock_sub.side_effect = [mock_toplevel, mock_porcelain, mock_diff]
        with pytest.raises(ValueError) as exc:
            with patch(
                "localforge.runtime.file_tools.SafeFileEditor._resolve",
                return_value=str(tmp_path / "f.txt"),
            ):
                await editor.write_text(str(tmp_path), "f.txt", "content")
        assert "Workspace file count budget exceeded" in str(exc.value)

        # 2. Simulate diff growth limit exceeded
        mock_porcelain_ok = MagicMock()
        mock_porcelain_ok.stdout = " M file1.txt\n"
        mock_sub.side_effect = [mock_toplevel, mock_porcelain_ok, mock_diff]

        with pytest.raises(ValueError) as exc:
            with patch(
                "localforge.runtime.file_tools.SafeFileEditor._resolve",
                return_value=str(tmp_path / "f.txt"),
            ):
                await editor.write_text(str(tmp_path), "f.txt", "content")
        assert "Workspace diff growth budget exceeded" in str(exc.value)


@pytest.mark.anyio
async def test_scheduler_watchdog_cleanup(tmp_path, db_session, db_manager):
    """Verify that stuck tasks (exceeding timeout duration) are
    terminated and cleaned up by watchdog.
    """
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="WatchdogProj", root_path=str(tmp_path), default_branch="main")
    )
    run = await uow.executions.create_run(
        domain.Run(project_id=proj.id, mode="unattended", initiated_by="test")
    )
    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-99", title="Stuck Task", description="")
    )

    await transition_task_to(uow, task.id, TaskStatus.IMPLEMENTING)

    task_run_data = domain.TaskRun(
        run_id=run.id,
        task_id=task.id,
        status=TaskRunStatus.RUNNING,
        worktree_path=str(tmp_path / "worktree"),
    )
    # Set started_at back in time to trigger watchdog
    task_run_data.started_at = datetime.now(UTC) - timedelta(hours=2)
    await uow.tasks.create_task_run(task_run_data)
    await uow.session.commit()

    scheduler = Scheduler(project_id=proj.id, run_id=run.id, db_manager=db_manager)

    await scheduler._process_iteration()
    await uow.session.commit()

    refreshed_task = await uow.tasks.get_task(task.id)
    # Watchdog still marks the task FAILED_SAFE immediately, but during
    # the same iteration the scheduler's recovery loop escalates the
    # task to BLOCKED_NEEDS_HUMAN_REVIEW when the recovery cycle
    # budget is exhausted.
    assert refreshed_task.status in (
        TaskStatus.FAILED_SAFE,
        TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
    )


@pytest.mark.anyio
async def test_scheduler_max_run_time(tmp_path, db_session, db_manager):
    """Verify that scheduler aborts the entire execution run if total
    elapsed time exceeds budget.
    """
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="RunTimeProj", root_path=str(tmp_path), default_branch="main")
    )
    run_data = domain.Run(
        project_id=proj.id,
        mode="unattended",
        initiated_by="test",
        status=RunStatus.RUNNING,
    )
    run_data.started_at = datetime.now(UTC) - timedelta(hours=3)
    run = await uow.executions.create_run(run_data)

    task = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-98", title="Timeout Task", description="")
    )
    await transition_task_to(uow, task.id, TaskStatus.IMPLEMENTING)

    task_run_data = domain.TaskRun(
        run_id=run.id,
        task_id=task.id,
        status=TaskRunStatus.RUNNING,
        worktree_path=str(tmp_path / "worktree"),
    )
    await uow.tasks.create_task_run(task_run_data)
    await uow.session.commit()

    scheduler = Scheduler(project_id=proj.id, run_id=run.id, db_manager=db_manager)

    await scheduler._process_iteration()
    await uow.session.commit()

    refreshed_run = await uow.executions.get_run(run.id)
    assert refreshed_run.status == RunStatus.FAILED
    assert "Run exceeded maximum run time budget" in refreshed_run.summary

    refreshed_task = await uow.tasks.get_task(task.id)
    # Task status may be FAILED_SAFE (failed by max-run-time) or
    # BLOCKED_NEEDS_HUMAN_REVIEW if recovery loop had a chance to run
    # during the same iteration.
    assert refreshed_task.status in (
        TaskStatus.FAILED_SAFE,
        TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
    )


@pytest.mark.anyio
async def test_scheduler_executes_ready_task_pipeline(tmp_path, db_session, db_manager):
    """Verify scheduler setup is followed by actual role pipeline execution."""
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="PipelineScheduler", root_path=str(tmp_path), default_branch="main")
    )
    assert proj.id is not None
    run = await uow.executions.create_run(
        domain.Run(
            project_id=proj.id,
            mode="unattended",
            initiated_by="test",
            status=RunStatus.RUNNING,
        )
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=proj.id,
            key="LF-2703",
            title="Pipeline execution",
            description="Run through scheduler",
            status=TaskStatus.READY,
            metadata={"changed_files": ["src/pipeline.py"]},
        )
    )
    assert task.id is not None
    await uow.session.commit()

    scheduler = Scheduler(
        project_id=proj.id,
        run_id=run.id,
        db_manager=db_manager,
        runner_pool=TaskRunnerPool([StubRunner(str(tmp_path))]),
        execute_pipeline=True,
    )

    await scheduler._process_iteration()
    await uow.session.commit()

    refreshed_task = await uow.tasks.get_task(task.id)
    assert refreshed_task is not None
    assert refreshed_task.status == TaskStatus.PR_READY
    task_runs = await uow.tasks.list_runs_for_task(task.id)
    assert task_runs
    task_run_id = task_runs[0].id
    assert task_run_id is not None
    artifacts = await uow.audits.list_artifacts_for_task_run(task_run_id)
    assert any(artifact.path.endswith("pr.md") for artifact in artifacts)
    refreshed_run = await uow.executions.get_run(run.id)
    assert refreshed_run is not None
    assert refreshed_run.status == RunStatus.RUNNING


@pytest.mark.anyio
async def test_scheduler_summary_generation(tmp_path, db_session, db_manager):
    """Verify scheduler compiles execution summary stats and outputs a markdown report."""
    uow = UnitOfWork(db_manager)
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)

    proj = await uow.projects.create_project(
        domain.Project(name="SummaryProj", root_path=str(tmp_path), default_branch="main")
    )
    run = await uow.executions.create_run(
        domain.Run(
            project_id=proj.id,
            mode="unattended",
            initiated_by="test",
            status=RunStatus.RUNNING,
            resource_limits={
                "recovery_cycles_used": 999,
                "paid_usd_spent_cached": 999.0,
            },
        )
    )

    # Task 1: DONE
    task1 = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-81", title="Task 1", description="")
    )
    await transition_task_to(uow, task1.id, TaskStatus.DONE)

    # Task 2: BLOCKED
    task2 = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-82", title="Task 2", description="")
    )
    await transition_task_to(uow, task2.id, TaskStatus.BLOCKED)

    # Task 3: FAILED_SAFE
    task3 = await uow.tasks.create_task(
        domain.Task(project_id=proj.id, key="LF-83", title="Task 3", description="")
    )
    await transition_task_to(uow, task3.id, TaskStatus.FAILED_SAFE)

    # Record Deny AuditEvent
    await uow.audits.append_audit_event(
        domain.AuditEvent(
            project_id=proj.id,
            run_id=run.id,
            actor_type=AuditEventActorType.SYSTEM,
            actor_id="safety-kernel",
            event_type=AuditEventType.SAFETY_DECISION,
            payload_redacted={
                "action": "run_command",
                "decision": "DENY",
                "reason": "Banned",
            },
        )
    )
    await uow.session.commit()

    scheduler = Scheduler(project_id=proj.id, run_id=run.id, db_manager=db_manager)

    await scheduler._process_iteration()
    await uow.session.commit()

    refreshed_run = await uow.executions.get_run(run.id)
    assert refreshed_run.status in (
        RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
        # Backwards compatibility for legacy expectations:
        RunStatus.FAILED,
    )
    assert "Tasks Needing Human Review" in refreshed_run.summary
    assert "Recovery cycles used" in refreshed_run.summary
    # Failed_Safe tasks are escalated by the recovery loop before
    # the summary is generated; they now appear under the
    # BLOCKED_NEEDS_HUMAN_REVIEW bucket.

    # Verify markdown file generation
    summary_file = tmp_path / "run_summary.md"
    assert summary_file.exists()
    content = summary_file.read_text(encoding="utf-8")
    assert "# LocalForge OS — Run Execution Summary" in content
    assert "**Run ID**: " in content


@pytest.mark.anyio
async def test_safe_file_editor_tolerates_missing_git_stdout(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from localforge.runtime.file_tools import SafeFileEditor

    editor = SafeFileEditor(UnitOfWork(), project_id=1, run_id=None, task_id=1)

    async def allow(*args, **kwargs):
        return None

    monkeypatch.setattr(editor, "_evaluate", allow)
    monkeypatch.setattr(editor, "_audit", allow)

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(stdout=str(tmp_path))
        return SimpleNamespace(stdout=None)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = await editor.write_text(str(tmp_path), "generated.py", "print('ok')\n")

    assert result.path.endswith("generated.py")
