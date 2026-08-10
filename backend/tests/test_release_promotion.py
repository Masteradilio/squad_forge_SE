from types import SimpleNamespace

import pytest
from localforge.core.config import LocalForgeConfig, ReleaseConfig
from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    ReleasePromotionMode,
    RunMode,
    RunStatus,
    TaskRunStatus,
    TaskStatus,
)
from localforge.services import release_promotion
from localforge.services.release_promotion import (
    POST_MERGE_AGENT_ORDER,
    ReleasePromotionService,
    ReleasePromotionState,
    build_release_plan,
    target_worktree_is_clean,
)


def test_release_defaults_to_human_approval() -> None:
    config = LocalForgeConfig()

    assert config.release.promotion_mode == ReleasePromotionMode.HUMAN_APPROVAL
    assert config.release.post_merge_agents == list(POST_MERGE_AGENT_ORDER)


def test_human_mode_waits_after_all_prs_are_ready() -> None:
    plan = build_release_plan(
        ReleaseConfig(promotion_mode=ReleasePromotionMode.HUMAN_APPROVAL),
        target_branch="main",
        current_branch="main",
        worktree_clean=True,
        task_branches=["localforge/lf-001-feature"],
        all_tasks_ready=True,
        approval_granted=False,
    )

    assert plan.state == ReleasePromotionState.WAITING_HUMAN_APPROVAL
    assert plan.can_merge is False


def test_full_access_can_merge_only_after_preconditions() -> None:
    plan = build_release_plan(
        ReleaseConfig(promotion_mode=ReleasePromotionMode.FULL_ACCESS),
        target_branch="main",
        current_branch="main",
        worktree_clean=True,
        task_branches=["localforge/lf-001-feature"],
        all_tasks_ready=True,
        approval_granted=False,
    )

    assert plan.state == ReleasePromotionState.READY_TO_MERGE
    assert plan.can_merge is True


def test_human_approval_unlocks_merge_without_changing_config() -> None:
    plan = build_release_plan(
        ReleaseConfig(promotion_mode=ReleasePromotionMode.HUMAN_APPROVAL),
        target_branch="main",
        current_branch="main",
        worktree_clean=True,
        task_branches=["localforge/lf-001-feature"],
        all_tasks_ready=True,
        approval_granted=True,
    )

    assert plan.state == ReleasePromotionState.READY_TO_MERGE
    assert plan.can_merge is True


def test_release_never_merges_when_main_is_dirty_or_tasks_are_incomplete() -> None:
    dirty_plan = build_release_plan(
        ReleaseConfig(promotion_mode=ReleasePromotionMode.FULL_ACCESS),
        target_branch="main",
        current_branch="main",
        worktree_clean=False,
        task_branches=["localforge/lf-001-feature"],
        all_tasks_ready=True,
        approval_granted=False,
    )
    incomplete_plan = build_release_plan(
        ReleaseConfig(promotion_mode=ReleasePromotionMode.FULL_ACCESS),
        target_branch="main",
        current_branch="main",
        worktree_clean=True,
        task_branches=["localforge/lf-001-feature"],
        all_tasks_ready=False,
        approval_granted=False,
    )

    assert dirty_plan.state == ReleasePromotionState.BLOCKED
    assert dirty_plan.can_merge is False
    assert incomplete_plan.state == ReleasePromotionState.BLOCKED
    assert incomplete_plan.can_merge is False


def test_target_clean_check_ignores_only_forgeos_runtime_artifacts() -> None:
    assert target_worktree_is_clean("?? .localforge/\n?? run_summary.md\n") is True
    assert target_worktree_is_clean(" M app/index.html\n") is False
    assert target_worktree_is_clean("?? user-notes.md\n") is False


class _FakeExecutionService:
    def __init__(self, run: domain.Run) -> None:
        self.run = run

    async def get_run(self, _run_id: int) -> domain.Run:
        return self.run

    async def update_run(self, run: domain.Run) -> domain.Run:
        self.run = run
        return run


class _FakeTaskService:
    def __init__(self, tasks: list[domain.Task], runs: dict[int, list[domain.TaskRun]]) -> None:
        self.tasks = tasks
        self.runs = runs

    async def list_tasks_for_project(self, _project_id: int) -> list[domain.Task]:
        return self.tasks

    async def list_runs_for_task(self, task_id: int) -> list[domain.TaskRun]:
        return self.runs.get(task_id, [])

    async def list_runs_for_run(self, run_id: int) -> list[domain.TaskRun]:
        return [
            task_run
            for task_runs in self.runs.values()
            for task_run in task_runs
            if task_run.run_id == run_id
        ]


class _FakeSafetyService:
    def __init__(self) -> None:
        self.approvals: list[domain.ActionApproval] = []

    async def list_approvals_for_run(self, _run_id: int) -> list[domain.ActionApproval]:
        return self.approvals

    async def create_approval(self, approval: domain.ActionApproval) -> domain.ActionApproval:
        approval.id = 91
        self.approvals.append(approval)
        return approval


class _FakeProjectService:
    def __init__(self, project: domain.Project) -> None:
        self.project = project

    async def get_project(self, _project_id: int) -> domain.Project:
        return self.project


class _FakeAuditService:
    async def append_audit_event(self, _event: domain.AuditEvent) -> None:
        return None


def _fake_uow(run: domain.Run) -> SimpleNamespace:
    project = domain.Project(
        id=7,
        name="release-test",
        root_path="C:/release-test",
        default_branch="main",
    )
    tasks = [
        domain.Task(id=1, project_id=7, key="LF-001", title="One", description="", status=TaskStatus.PR_READY),
        domain.Task(id=2, project_id=7, key="LF-002", title="Two", description="", status=TaskStatus.PR_READY),
    ]
    task_runs = {
        1: [domain.TaskRun(id=11, run_id=run.id or 1, task_id=1, status=TaskRunStatus.COMPLETED, branch_name="localforge/lf-001")],
        2: [domain.TaskRun(id=12, run_id=run.id or 1, task_id=2, status=TaskRunStatus.COMPLETED, branch_name="localforge/lf-002")],
    }
    return SimpleNamespace(
        executions=_FakeExecutionService(run),
        projects=_FakeProjectService(project),
        tasks=_FakeTaskService(tasks, task_runs),
        safety=_FakeSafetyService(),
        audits=_FakeAuditService(),
    )


class _FakeGit:
    def __init__(self) -> None:
        self.merged: list[str] = []

    async def current_branch(self) -> str:
        return "main"

    async def status_porcelain(self) -> str:
        return ""

    async def branch_exists(self, _branch: str) -> bool:
        return True

    async def merge_branch(self, branch: str) -> None:
        self.merged.append(branch)

    async def merge_abort(self) -> None:
        return None

    async def current_commit_hash(self) -> str:
        return "merge-commit-1"


@pytest.mark.anyio
async def test_human_mode_pauses_and_persists_release_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    run = domain.Run(
        id=41,
        project_id=7,
        mode=RunMode.UNATTENDED,
        status=RunStatus.RUNNING,
        initiated_by="test",
        resource_limits={
            "release": ReleaseConfig().model_dump(mode="json"),
        },
    )
    run.resource_limits["release"]["promotion_mode"] = ReleasePromotionMode.HUMAN_APPROVAL.value
    uow = _fake_uow(run)
    monkeypatch.setattr(release_promotion, "GitAdapter", lambda **_: _FakeGit())

    result = await ReleasePromotionService(uow, project_id=7, run_id=41).promote()

    assert result.state == ReleasePromotionState.WAITING_HUMAN_APPROVAL
    assert run.status == RunStatus.PAUSED
    assert uow.safety.approvals[0].status == ActionApprovalStatus.PENDING
    assert run.resource_limits["release_promotion"]["approval_id"] == 91


@pytest.mark.anyio
async def test_full_access_merges_and_runs_post_merge_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    run = domain.Run(
        id=42,
        project_id=7,
        mode=RunMode.UNATTENDED,
        status=RunStatus.RUNNING,
        initiated_by="test",
        resource_limits={
            "release": ReleaseConfig(
                promotion_mode=ReleasePromotionMode.FULL_ACCESS
            ).model_dump(mode="json"),
        },
    )
    uow = _fake_uow(run)
    fake_git = _FakeGit()
    monkeypatch.setattr(release_promotion, "GitAdapter", lambda **_: fake_git)
    calls: list[str] = []

    async def command_runner(**kwargs: object) -> tuple[int, str, str]:
        calls.append(str(kwargs["command"]))
        return 0, "passed", ""

    result = await ReleasePromotionService(
        uow,
        project_id=7,
        run_id=42,
        command_runner=command_runner,
    ).promote()

    assert result.state == ReleasePromotionState.COMPLETED
    assert fake_git.merged == ["localforge/lf-001", "localforge/lf-002"]
    assert calls == ["python -m pytest -q", "python scripts/check_security_scans.py"]
    assert run.resource_limits["release_promotion"]["state"] == "COMPLETED"


@pytest.mark.anyio
async def test_release_does_not_promote_branch_from_another_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = domain.Run(
        id=43,
        project_id=7,
        mode=RunMode.UNATTENDED,
        status=RunStatus.RUNNING,
        initiated_by="test",
        resource_limits={
            "release": ReleaseConfig(
                promotion_mode=ReleasePromotionMode.FULL_ACCESS
            ).model_dump(mode="json"),
        },
    )
    uow = _fake_uow(run)
    uow.tasks.runs[1] = [
        domain.TaskRun(
            id=10,
            run_id=42,
            task_id=1,
            status=TaskRunStatus.COMPLETED,
            branch_name="localforge/old-run-branch",
        )
    ]
    fake_git = _FakeGit()
    monkeypatch.setattr(release_promotion, "GitAdapter", lambda **_: fake_git)

    result = await ReleasePromotionService(
        uow,
        project_id=7,
        run_id=43,
        command_runner=lambda **_: _passed_command(),
    ).promote()

    assert result.state == ReleasePromotionState.COMPLETED
    assert fake_git.merged == ["localforge/lf-002"]
    assert "localforge/old-run-branch" not in fake_git.merged


async def _passed_command() -> tuple[int, str, str]:
    return 0, "passed", ""
