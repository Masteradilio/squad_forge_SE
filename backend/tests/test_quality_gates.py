import pytest
from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    ActionKind,
    RunMode,
    TaskStatus,
)
from localforge.quality.discovery import TestCommandDiscovery
from localforge.quality.gates import QualityGateEvaluator
from localforge.quality.runner import FocusedTestRunner
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.safety import SafetyService
from localforge.services.task import TaskService
from localforge.storage import UnitOfWork


def test_test_command_discovery_detects_common_commands_and_project_overrides(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest","lint":"eslint ."}}',
        encoding="utf-8",
    )
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "config.yaml").write_text(
        "quality:\n  test_commands:\n    - python -m pytest custom -q\n",
        encoding="utf-8",
    )

    commands = TestCommandDiscovery().discover(tmp_path)

    assert commands[0].command == "python -m pytest custom -q"
    assert any(command.command == "python -m pytest" for command in commands)
    assert any(command.command == "npm test" for command in commands)
    assert any(command.command == "npm run lint" for command in commands)


@pytest.mark.anyio
async def test_focused_test_runner_captures_output_timeout_and_writes_test_artifact(
    db_session, tmp_path
):
    uow = bind_uow(db_session)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    import git

    git.Repo.init(str(worktree))
    project = await uow.projects.create_project(  # type: ignore[union-attr]
        domain.Project(name="Quality", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(  # type: ignore[union-attr]
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    task = await uow.tasks.create_task(  # type: ignore[union-attr]
        domain.Task(project_id=project.id, key="LF-1102", title="Run tests", description="")
    )
    assert run.id is not None
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(  # type: ignore[union-attr]
        domain.TaskRun(run_id=run.id, task_id=task.id, worktree_path=str(worktree))
    )
    assert task_run.id is not None

    result = await FocusedTestRunner(uow, project_id=project.id, run_id=run.id).run(
        task_id=task.id,
        task_run_id=task_run.id,
        worktree_path=str(worktree),
        command="git status",
        timeout=10.0,
    )

    assert result.exit_code == 0
    artifacts = await uow.audits.list_artifacts_for_task_run(task_run.id)  # type: ignore[union-attr]
    assert artifacts and artifacts[0].path.endswith("tests.md")


@pytest.mark.anyio
async def test_quality_gate_blocks_pr_ready_on_failed_tests(db_session, tmp_path):
    uow = bind_uow(db_session)
    project, run, task, task_run = await seed_quality_task(uow, tmp_path, TaskStatus.TESTING)
    assert project.id is not None
    assert run.id is not None
    assert task.id is not None
    assert task_run.id is not None

    result = await QualityGateEvaluator(uow, project_id=project.id, run_id=run.id).evaluate(
        task_id=task.id,
        task_run_id=task_run.id,
        test_results=[{"command": "pytest", "exit_code": 1}],
    )

    assert result.allowed is False
    assert "failed tests" in result.reasons
    refreshed = await uow.tasks.get_task(task.id)  # type: ignore[union-attr]
    assert refreshed is not None
    assert refreshed.status == TaskStatus.BLOCKED


@pytest.mark.anyio
async def test_quality_gate_allows_missing_tests_only_with_risk_note(db_session, tmp_path):
    uow = bind_uow(db_session)
    project, run, task, task_run = await seed_quality_task(uow, tmp_path, TaskStatus.TESTING)
    assert project.id is not None
    assert run.id is not None
    assert task.id is not None
    assert task_run.id is not None

    blocked = await QualityGateEvaluator(uow, project_id=project.id, run_id=run.id).evaluate(
        task_id=task.id,
        task_run_id=task_run.id,
        test_results=[],
    )
    assert blocked.allowed is False
    assert "missing tests" in blocked.reasons

    task.metadata["quality_risk_note"] = "Docs-only change; no executable tests."
    await uow.tasks.update_task(task)  # type: ignore[union-attr]
    allowed = await QualityGateEvaluator(uow, project_id=project.id, run_id=run.id).evaluate(
        task_id=task.id,
        task_run_id=task_run.id,
        test_results=[],
    )

    assert allowed.allowed is True


@pytest.mark.anyio
async def test_quality_gate_requires_approval_for_protected_file_changes(db_session, tmp_path):
    uow = bind_uow(db_session)
    project, run, task, task_run = await seed_quality_task(uow, tmp_path, TaskStatus.TESTING)
    assert project.id is not None
    assert run.id is not None
    assert task.id is not None
    assert task_run.id is not None
    task.metadata["changed_files"] = [".env"]
    task.metadata["quality_risk_note"] = "Secret template change reviewed."
    await uow.tasks.update_task(task)  # type: ignore[union-attr]

    blocked = await QualityGateEvaluator(uow, project_id=project.id, run_id=run.id).evaluate(
        task_id=task.id,
        task_run_id=task_run.id,
        test_results=[{"command": "pytest", "exit_code": 0}],
    )
    assert blocked.allowed is False
    assert "protected file approval required" in blocked.reasons

    await uow.safety.create_approval(  # type: ignore[union-attr]
        domain.ActionApproval(
            project_id=project.id,
            run_id=run.id,
            task_id=task.id,
            action_kind=ActionKind.WRITE_FILE,
            payload={"path": ".env"},
            purpose="approve protected change",
            risk_level="high",
            status=ActionApprovalStatus.APPROVED,
            decided_by="tester",
        )
    )
    allowed = await QualityGateEvaluator(uow, project_id=project.id, run_id=run.id).evaluate(
        task_id=task.id,
        task_run_id=task_run.id,
        test_results=[{"command": "pytest", "exit_code": 0}],
    )
    assert allowed.allowed is True


@pytest.mark.anyio
async def test_quality_gate_blocks_likely_secret_changes(db_session, tmp_path):
    uow = bind_uow(db_session)
    project, run, task, task_run = await seed_quality_task(uow, tmp_path, TaskStatus.TESTING)
    assert project.id is not None
    assert run.id is not None
    assert task.id is not None
    assert task_run.id is not None
    secret_file = tmp_path / "config.py"
    secret_file.write_text('API_TOKEN="abc123456789SECRET"\n', encoding="utf-8")
    task.metadata["changed_files"] = ["config.py"]
    await uow.tasks.update_task(task)  # type: ignore[union-attr]

    blocked = await QualityGateEvaluator(uow, project_id=project.id, run_id=run.id).evaluate(
        task_id=task.id,
        task_run_id=task_run.id,
        test_results=[{"command": "pytest", "exit_code": 0}],
    )

    assert blocked.allowed is False
    assert "likely secret detected" in blocked.reasons


def bind_uow(db_session) -> UnitOfWork:
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)
    return uow


async def seed_quality_task(
    uow: UnitOfWork,
    tmp_path,
    status: TaskStatus,
) -> tuple[domain.Project, domain.Run, domain.Task, domain.TaskRun]:
    project = await uow.projects.create_project(  # type: ignore[union-attr]
        domain.Project(name="Gate", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(  # type: ignore[union-attr]
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(  # type: ignore[union-attr]
        domain.Task(project_id=project.id, key="LF-1103", title="Gate", description="")
    )
    assert task.id is not None
    task_id = task.id
    await uow.tasks.update_task_status(task_id, TaskStatus.READY)  # type: ignore[union-attr]
    await uow.tasks.update_task_status(task_id, TaskStatus.CLAIMED)  # type: ignore[union-attr]
    await uow.tasks.update_task_status(task_id, TaskStatus.PLANNING)  # type: ignore[union-attr]
    await uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)  # type: ignore[union-attr]
    if status == TaskStatus.TESTING:
        task = await uow.tasks.update_task_status(task_id, TaskStatus.TESTING)  # type: ignore[union-attr]
    task_run = await uow.tasks.create_task_run(  # type: ignore[union-attr]
        domain.TaskRun(run_id=run.id, task_id=task_id, worktree_path=str(tmp_path))
    )
    return project, run, task, task_run
