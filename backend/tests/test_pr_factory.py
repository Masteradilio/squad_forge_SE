import pytest
from localforge.models import domain
from localforge.models.enums import RunMode, TaskStatus
from localforge.pr_factory.github import GitHubPRAdapter
from localforge.pr_factory.local import LocalPRFactory
from localforge.services.audit import AuditService
from localforge.services.cost_benchmark import CostBenchmarkService
from localforge.services.execution import ExecutionService
from localforge.services.maker_checker import MakerCheckerService
from localforge.services.project import ProjectService
from localforge.services.task import TaskService
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@pytest.mark.anyio
async def test_pr_factory_generates_pr_artifact_with_evidence_paths(db_session, tmp_path):
    uow, project, run, task, task_run = await seed_pr_task(db_session, tmp_path)
    assert project.id is not None and run.id is not None and task.id is not None
    assert task_run.id is not None
    await write_required_evidence(uow, str(tmp_path), run.id, task_run.id, task.key)

    result = await LocalPRFactory(uow, project_id=project.id, run_id=run.id).generate(
        task_id=task.id,
        task_run_id=task_run.id,
    )

    assert result.ready is True
    assert result.artifact_path.endswith("pr.md")
    pr_body = await ArtifactStore(uow).read_artifact(str(tmp_path), run.id, task.key, "pr.md")
    assert "# LF-1301: PR Factory" in pr_body
    assert "Acceptance Criteria" in pr_body
    assert "tests.md" in pr_body
    assert "risk.md" in pr_body
    assert "diff.patch" in pr_body
    assert "Checklist" in pr_body


@pytest.mark.anyio
async def test_pr_factory_marks_task_pr_ready_without_remote_github(db_session, tmp_path):
    uow, project, run, task, task_run = await seed_pr_task(db_session, tmp_path)
    assert project.id is not None and run.id is not None and task.id is not None
    assert task_run.id is not None
    await write_required_evidence(uow, str(tmp_path), run.id, task_run.id, task.key)

    result = await LocalPRFactory(uow, project_id=project.id, run_id=run.id).generate(
        task_id=task.id,
        task_run_id=task_run.id,
    )

    refreshed = await uow.tasks.get_task(task.id)  # type: ignore[union-attr]
    assert result.ready is True
    assert refreshed is not None
    assert refreshed.status == TaskStatus.PR_READY
    assert result.remote_url is None


def test_github_pr_adapter_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv("LOCALFORGE_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("LOCALFORGE_ENABLE_GITHUB_PR", raising=False)

    adapter = GitHubPRAdapter.from_environment()

    assert adapter.enabled is False
    assert adapter.create_pr(title="Title", body="Body", branch="branch") is None


@pytest.mark.anyio
async def test_pr_factory_falls_back_to_local_artifact_when_github_disabled(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.delenv("LOCALFORGE_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("LOCALFORGE_ENABLE_GITHUB_PR", raising=False)
    uow, project, run, task, task_run = await seed_pr_task(db_session, tmp_path)
    assert project.id is not None and run.id is not None and task.id is not None
    assert task_run.id is not None
    await write_required_evidence(uow, str(tmp_path), run.id, task_run.id, task.key)

    result = await LocalPRFactory(
        uow,
        project_id=project.id,
        run_id=run.id,
        github_adapter=GitHubPRAdapter.from_environment(),
    ).generate(task_id=task.id, task_run_id=task_run.id)

    assert result.ready is True
    assert result.remote_url is None
    assert result.artifact_path.endswith("pr.md")


async def seed_pr_task(db_session, tmp_path):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.maker_checker = MakerCheckerService(db_session)
    uow.audits = AuditService(db_session)
    uow.cost_benchmark = CostBenchmarkService(db_session)
    project = await uow.projects.create_project(
        domain.Project(name="PR", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-1301",
            title="PR Factory",
            description="Create PR artifacts",
            acceptance_criteria=["artifact generated", "task marked PR_READY"],
            status=TaskStatus.REVIEWING,
            metadata={
                "changed_files": ["backend/localforge/pr_factory/local.py"],
                "source_commit": "source-commit",
                "target_commit": "target-commit",
            },
        )
    )
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(
        domain.TaskRun(
            run_id=run.id,
            task_id=task.id,
            worktree_path=str(tmp_path),
            branch_name="localforge/lf-1301-pr-factory",
            final_summary="Implemented PR Factory.",
        )
    )
    return uow, project, run, task, task_run


async def write_required_evidence(
    uow: UnitOfWork,
    project_root: str,
    run_id: int,
    task_run_id: int,
    task_key: str,
) -> None:
    store = ArtifactStore(uow)
    await store.write_artifact(
        project_root,
        task_run_id,
        task_key,
        run_id,
        "diff.patch",
        "diff --git a/file b/file\n",
        "Diff",
    )
    await store.write_artifact(
        project_root,
        task_run_id,
        task_key,
        run_id,
        "tests.md",
        "pytest passed",
        "Tests",
    )
    await store.write_artifact(
        project_root,
        task_run_id,
        task_key,
        run_id,
        "risk.md",
        "Allowed: True",
        "Risk",
    )
    assert uow.maker_checker is not None
    verification = await uow.maker_checker.create_verification(
        project_id=1,
        task_run_id=task_run_id,
        maker_agent_id="coder-agent",
        checker_agent_id="reviewer-agent",
    )
    assert verification.id is not None
    await uow.maker_checker.submit_verification_result(
        verification_id=verification.id,
        checker_agent_id="reviewer-agent",
        approved=True,
        deterministic_passed=True,
        tests_executed=["pytest"],
        not_checked=[],
        feedback="Observed test evidence passed.",
    )
