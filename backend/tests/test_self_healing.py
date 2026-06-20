import pytest
from localforge.healing.classifier import FailureClass, FailureClassifier
from localforge.healing.engine import SelfHealingEngine
from localforge.healing.policy import RepairPolicy, RepairPolicyState
from localforge.models import domain
from localforge.models.enums import RunMode, TaskStatus
from localforge.quality.runner import TestRunResult
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.safety import SafetyService
from localforge.services.task import TaskService
from localforge.storage import UnitOfWork


class SequenceRunner:
    def __init__(self, results: list[TestRunResult]):
        self.results = results
        self.calls = 0

    async def run(self, **kwargs) -> TestRunResult:
        result = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return result


def test_failure_classifier_handles_representative_logs():
    classifier = FailureClassifier()

    assert classifier.classify("pytest", "E AssertionError: expected 1", "") == (
        FailureClass.TEST_ASSERTION_FAILURE
    )
    assert classifier.classify("mypy backend", "", "error: Incompatible types") == (
        FailureClass.TYPECHECK_FAILURE
    )
    assert classifier.classify("ruff check backend", "", "F401 imported but unused") == (
        FailureClass.LINT_FAILURE
    )
    assert classifier.classify("pytest", "", "ModuleNotFoundError: No module named 'x'") == (
        FailureClass.IMPORT_ERROR
    )
    assert classifier.classify("git status", "", "Action DENIED by Safety Kernel") == (
        FailureClass.COMMAND_BLOCKED_BY_POLICY
    )


def test_repair_policy_stops_on_max_attempts_repeated_failure_diff_growth_and_safety_denial():
    policy = RepairPolicy(max_attempts=2, max_diff_growth=20)
    state = RepairPolicyState()

    assert policy.can_attempt(state, FailureClass.TEST_ASSERTION_FAILURE, 5).allowed is True
    state = state.record(FailureClass.TEST_ASSERTION_FAILURE, 5)
    assert policy.can_attempt(state, FailureClass.TEST_ASSERTION_FAILURE, 5).allowed is False
    assert (
        policy.can_attempt(RepairPolicyState(attempt_count=2), FailureClass.LINT_FAILURE, 1).allowed
        is False
    )
    assert policy.can_attempt(RepairPolicyState(), FailureClass.LINT_FAILURE, 21).allowed is False
    assert (
        policy.can_attempt(RepairPolicyState(), FailureClass.COMMAND_BLOCKED_BY_POLICY, 1).allowed
        is False
    )


@pytest.mark.anyio
async def test_self_healing_repairs_simple_failing_fixture(db_session, tmp_path):
    uow, project, run, task, task_run = await seed_repair_task(db_session, tmp_path)
    worktree = tmp_path / "worktree"
    target = worktree / "answer.txt"
    target.write_text("bad\n", encoding="utf-8")
    assert project.id is not None and run.id is not None and task.id is not None
    assert task_run.id is not None
    task.metadata["repair_actions"] = [
        {"path": "answer.txt", "content": "good\n", "failure_class": "TEST_ASSERTION_FAILURE"}
    ]
    await uow.tasks.update_task(task)  # type: ignore[union-attr]

    engine = SelfHealingEngine(
        uow,
        project_id=project.id,
        run_id=run.id,
        runner=SequenceRunner(
            [
                TestRunResult("pytest", 1, "", "AssertionError: bad"),
                TestRunResult("pytest", 0, "passed", ""),
            ]
        ),
    )

    result = await engine.repair_task(
        task_id=task.id,
        task_run_id=task_run.id,
        worktree_path=str(worktree),
        test_command="pytest",
    )

    assert result.repaired is True
    assert target.read_text(encoding="utf-8") == "good\n"
    refreshed = await uow.tasks.get_task(task.id)  # type: ignore[union-attr]
    assert refreshed is not None
    assert refreshed.status == TaskStatus.TESTING
    artifacts = await uow.audits.list_artifacts_for_task_run(task_run.id)  # type: ignore[union-attr]
    assert any(artifact.path.endswith("repair.md") for artifact in artifacts)


@pytest.mark.anyio
async def test_self_healing_blocks_safely_when_unable(db_session, tmp_path):
    uow, project, run, task, task_run = await seed_repair_task(db_session, tmp_path)
    assert project.id is not None and run.id is not None and task.id is not None
    assert task_run.id is not None
    engine = SelfHealingEngine(
        uow,
        project_id=project.id,
        run_id=run.id,
        runner=SequenceRunner([TestRunResult("pytest", 1, "", "AssertionError: bad")]),
    )

    result = await engine.repair_task(
        task_id=task.id,
        task_run_id=task_run.id,
        worktree_path=str(tmp_path / "worktree"),
        test_command="pytest",
    )

    assert result.repaired is False
    refreshed = await uow.tasks.get_task(task.id)  # type: ignore[union-attr]
    assert refreshed is not None
    assert refreshed.status == TaskStatus.FAILED_SAFE
    artifacts = await uow.audits.list_artifacts_for_task_run(task_run.id)  # type: ignore[union-attr]
    assert any(artifact.path.endswith("blocker.md") for artifact in artifacts)


@pytest.mark.anyio
async def test_self_healing_rolls_back_bad_repair_and_audits(db_session, tmp_path):
    uow, project, run, task, task_run = await seed_repair_task(db_session, tmp_path)
    worktree = tmp_path / "worktree"
    target = worktree / "answer.txt"
    target.write_text("bad\n", encoding="utf-8")
    assert project.id is not None and run.id is not None and task.id is not None
    assert task_run.id is not None
    task.metadata["repair_actions"] = [
        {"path": "answer.txt", "content": "worse\n", "failure_class": "TEST_ASSERTION_FAILURE"}
    ]
    await uow.tasks.update_task(task)  # type: ignore[union-attr]
    engine = SelfHealingEngine(
        uow,
        project_id=project.id,
        run_id=run.id,
        runner=SequenceRunner(
            [
                TestRunResult("pytest", 1, "", "AssertionError: bad"),
                TestRunResult("pytest", 1, "", "SyntaxError: worse"),
            ]
        ),
    )

    result = await engine.repair_task(
        task_id=task.id,
        task_run_id=task_run.id,
        worktree_path=str(worktree),
        test_command="pytest",
    )

    assert result.repaired is False
    assert target.read_text(encoding="utf-8") == "bad\n"
    events = await uow.audits.list_audit_events_for_project(project.id)  # type: ignore[union-attr]
    assert any(event.payload_redacted.get("action") == "repair_rollback" for event in events)


async def seed_repair_task(db_session, tmp_path):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = await uow.projects.create_project(
        domain.Project(name="Heal", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=project.id, key="LF-1203", title="Repair", description="")
    )
    assert task.id is not None
    task_id = task.id
    await uow.tasks.update_task_status(task_id, TaskStatus.READY)
    await uow.tasks.update_task_status(task_id, TaskStatus.CLAIMED)
    await uow.tasks.update_task_status(task_id, TaskStatus.PLANNING)
    await uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)
    task = await uow.tasks.update_task_status(task_id, TaskStatus.TESTING)
    task_run = await uow.tasks.create_task_run(
        domain.TaskRun(run_id=run.id, task_id=task_id, worktree_path=str(worktree))
    )
    return uow, project, run, task, task_run
