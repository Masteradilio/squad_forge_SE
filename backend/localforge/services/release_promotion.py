"""Governed promotion from task-level PR_READY evidence to a tested main branch.

The implementation intentionally keeps release authority separate from task
execution.  A task can produce PR_READY evidence without gaining permission to
merge.  Promotion is then either paused for an explicit human approval or
performed by the opt-in full-access policy, and both paths run the same
post-merge Tester and SafetyAuditor checks.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from localforge.core.config import ReleaseConfig, load_config
from localforge.gitops.adapter import GitAdapter
from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    ActionKind,
    AuditEventActorType,
    AuditEventType,
    ReleasePromotionMode,
    RunMode,
    RunStatus,
    TaskStatus,
)
from localforge.safety.runner import run_safe_command
from localforge.services.operational_profiles import profile_manifest
from localforge.services.release_audit import ReleaseTreeAuditor
from localforge.storage import UnitOfWork

POST_MERGE_AGENT_ORDER = ("Tester", "SafetyAuditor")
RELEASE_METADATA_KEY = "release_promotion"
# These paths are created by the ForgeOS runtime in the project checkout. They
# are evidence/state, not product changes, and must not prevent full-access
# promotion when a sparse benchmark workspace does not carry the repository's
# .gitignore yet. User-owned files remain blocking by default.
RUNTIME_GENERATED_TARGET_PATHS = frozenset({"run_summary.md"})
RUNTIME_GENERATED_TARGET_PREFIXES = (".localforge/",)


class ReleasePromotionState(StrEnum):
    WAITING_HUMAN_APPROVAL = "WAITING_HUMAN_APPROVAL"
    READY_TO_MERGE = "READY_TO_MERGE"
    MERGING = "MERGING"
    POST_MERGE_TESTING = "POST_MERGE_TESTING"
    POST_MERGE_SECURITY = "POST_MERGE_SECURITY"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReleasePromotionPlan:
    state: ReleasePromotionState
    can_merge: bool
    reason: str
    target_branch: str
    task_branches: list[str] = field(default_factory=list)
    post_merge_agents: tuple[str, ...] = POST_MERGE_AGENT_ORDER


@dataclass(frozen=True)
class ReleasePromotionResult:
    state: ReleasePromotionState
    reason: str
    approval_id: int | None = None
    merge_commit: str | None = None
    post_merge_results: list[dict[str, Any]] = field(default_factory=list)


def build_release_plan(
    config: ReleaseConfig,
    *,
    target_branch: str,
    current_branch: str,
    worktree_clean: bool,
    task_branches: list[str],
    all_tasks_ready: bool,
    approval_granted: bool,
) -> ReleasePromotionPlan:
    """Calculate the only states in which release promotion may proceed."""

    if not all_tasks_ready:
        return ReleasePromotionPlan(
            state=ReleasePromotionState.BLOCKED,
            can_merge=False,
            reason="All implementation tasks must be PR_READY or DONE before promotion.",
            target_branch=target_branch,
            task_branches=task_branches,
            post_merge_agents=tuple(config.post_merge_agents),
        )
    if config.require_clean_target and not worktree_clean:
        return ReleasePromotionPlan(
            state=ReleasePromotionState.BLOCKED,
            can_merge=False,
            reason=f"Target branch '{target_branch}' has uncommitted changes.",
            target_branch=target_branch,
            task_branches=task_branches,
            post_merge_agents=tuple(config.post_merge_agents),
        )
    if current_branch != target_branch:
        return ReleasePromotionPlan(
            state=ReleasePromotionState.BLOCKED,
            can_merge=False,
            reason=(
                f"Promotion must run on target branch '{target_branch}', "
                f"but the repository is on '{current_branch}'."
            ),
            target_branch=target_branch,
            task_branches=task_branches,
            post_merge_agents=tuple(config.post_merge_agents),
        )
    if config.promotion_mode == ReleasePromotionMode.HUMAN_APPROVAL and not approval_granted:
        return ReleasePromotionPlan(
            state=ReleasePromotionState.WAITING_HUMAN_APPROVAL,
            can_merge=False,
            reason="Human approval is required before merging PR_READY branches.",
            target_branch=target_branch,
            task_branches=task_branches,
            post_merge_agents=tuple(config.post_merge_agents),
        )
    return ReleasePromotionPlan(
        state=ReleasePromotionState.READY_TO_MERGE,
        can_merge=True,
        reason=(
            "Explicit full-access promotion policy enabled."
            if config.promotion_mode == ReleasePromotionMode.FULL_ACCESS
            else "Human release approval is persisted and valid."
        ),
        target_branch=target_branch,
        task_branches=task_branches,
        post_merge_agents=tuple(config.post_merge_agents),
    )


CommandRunner = Callable[..., Awaitable[tuple[int, str, str]]]


def target_worktree_is_clean(status_porcelain: str) -> bool:
    """Return whether target changes contain anything outside ForgeOS runtime state.

    ``git status --porcelain`` reports ignored runtime directories as untracked
    in sparse benchmark repositories that do not have the root ``.gitignore``
    copied into them. Release promotion must still fail closed for user-owned
    changes, so only the two explicitly generated runtime forms are filtered.
    """

    for raw_line in status_porcelain.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Porcelain v1 uses two status columns followed by a path. For rename
        # entries, the destination path is the final path and is the one that
        # can be safely evaluated here.
        path = line[3:].strip() if len(line) >= 3 else line
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1].strip()
        normalized = path.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in RUNTIME_GENERATED_TARGET_PATHS:
            continue
        if any(normalized.startswith(prefix) for prefix in RUNTIME_GENERATED_TARGET_PREFIXES):
            continue
        return False
    return True


class ReleasePromotionService:
    """Promote all PR_READY task branches and run post-merge release agents."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        project_id: int,
        run_id: int,
        command_runner: CommandRunner = run_safe_command,
    ) -> None:
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id
        self.command_runner = command_runner

    async def promote(self, *, approval_granted: bool = False) -> ReleasePromotionResult:
        assert self.uow.executions is not None
        assert self.uow.projects is not None
        assert self.uow.tasks is not None
        assert self.uow.safety is not None
        run = await self.uow.executions.get_run(self.run_id)
        project = await self.uow.projects.get_project(self.project_id)
        tasks = await self.uow.tasks.list_tasks_for_project(self.project_id)
        if run is None or project is None:
            return ReleasePromotionResult(ReleasePromotionState.BLOCKED, "Run or project not found.")

        # Runs created before release promotion existed do not have a frozen
        # release policy. Preserve their historical PR_READY completion
        # semantics; every new CLI run snapshots ``release`` explicitly.
        if "release" not in (run.resource_limits or {}):
            return ReleasePromotionResult(
                ReleasePromotionState.COMPLETED,
                "Legacy run without a release promotion policy; no merge performed.",
            )

        existing_release = self._release_metadata(run)
        if existing_release.get("state") == ReleasePromotionState.COMPLETED.value:
            return ReleasePromotionResult(
                ReleasePromotionState.COMPLETED,
                str(run.summary or "Release promotion already completed."),
                merge_commit=existing_release.get("merge_commit"),
                post_merge_results=list(existing_release.get("post_merge_results") or []),
            )

        config = self._release_config(run)
        task_runs = await self.uow.tasks.list_runs_for_run(self.run_id)
        run_task_ids = {task_run.task_id for task_run in task_runs}
        run_tasks = [task for task in tasks if task.id in run_task_ids]
        task_branches = self._task_branches(run_tasks, task_runs)
        pr_ready_tasks = [task for task in run_tasks if task.status == TaskStatus.PR_READY]
        all_tasks_ready = bool(run_tasks) and all(
            task.status in {TaskStatus.PR_READY, TaskStatus.DONE} for task in run_tasks
        ) and len(task_branches) == len(pr_ready_tasks)
        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            run_mode=RunMode.UNATTENDED,
            repository_root=project.root_path,
        )
        target_branch = config.target_branch or project.default_branch
        current_branch = await git.current_branch()
        worktree_clean = target_worktree_is_clean(await git.status_porcelain())
        approval = await self._release_approval(config, task_branches)
        approval_granted = approval_granted or bool(
            approval and approval.status == ActionApprovalStatus.APPROVED
        )
        plan = build_release_plan(
            config,
            target_branch=target_branch,
            current_branch=current_branch,
            worktree_clean=worktree_clean,
            task_branches=task_branches,
            all_tasks_ready=all_tasks_ready,
            approval_granted=approval_granted,
        )

        if plan.state == ReleasePromotionState.WAITING_HUMAN_APPROVAL:
            approval = approval or await self._create_release_approval(
                config, task_branches, target_branch
            )
            await self._record_release_state(
                run,
                state=plan.state,
                reason=plan.reason,
                approval_id=approval.id if approval else None,
                approval_granted=False,
                target_branch=target_branch,
                task_branches=task_branches,
            )
            run.status = RunStatus.PAUSED
            run.summary = (
                f"{plan.reason} Approval ID: {approval.id if approval else 'unavailable'}."
            )
            await self.uow.executions.update_run(run)
            return ReleasePromotionResult(
                state=plan.state,
                reason=plan.reason,
                approval_id=approval.id if approval else None,
            )

        if plan.state == ReleasePromotionState.BLOCKED:
            await self._record_release_state(
                run,
                state=plan.state,
                reason=plan.reason,
                target_branch=target_branch,
                task_branches=task_branches,
            )
            run.status = RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW
            run.summary = plan.reason
            await self.uow.executions.update_run(run)
            return ReleasePromotionResult(state=plan.state, reason=plan.reason)

        return await self._merge_and_validate(
            run,
            project,
            config,
            plan,
            run_tasks=run_tasks,
            approval_granted=approval_granted,
        )

    @staticmethod
    def _task_branches(
        tasks: list[domain.Task], task_runs: list[domain.TaskRun]
    ) -> list[str]:
        runs_by_task: dict[int, list[domain.TaskRun]] = {}
        for task_run in task_runs:
            runs_by_task.setdefault(task_run.task_id, []).append(task_run)
        branches: list[str] = []
        for task in tasks:
            if task.status not in {TaskStatus.PR_READY, TaskStatus.DONE} or task.id is None:
                continue
            runs = runs_by_task.get(task.id, [])
            latest = max(runs, key=lambda item: item.id or 0) if runs else None
            if latest and latest.branch_name:
                branches.append(latest.branch_name)
        return list(dict.fromkeys(branches))

    @staticmethod
    def _release_config(run: domain.Run) -> ReleaseConfig:
        snapshot = dict((run.resource_limits or {}).get("release") or {})
        if snapshot:
            return ReleaseConfig.model_validate(snapshot)
        return load_config().release

    async def _release_approval(
        self, config: ReleaseConfig, task_branches: list[str]
    ) -> domain.ActionApproval | None:
        if config.promotion_mode != ReleasePromotionMode.HUMAN_APPROVAL:
            return None
        assert self.uow.safety is not None
        key = self._approval_key(config, task_branches)
        approvals = await self.uow.safety.list_approvals_for_run(self.run_id)
        return next((item for item in approvals if item.idempotency_key == key), None)

    async def _create_release_approval(
        self, config: ReleaseConfig, task_branches: list[str], target_branch: str
    ) -> domain.ActionApproval:
        assert self.uow.safety is not None
        key = self._approval_key(config, task_branches)
        approval = domain.ActionApproval(
            project_id=self.project_id,
            run_id=self.run_id,
            action_kind=ActionKind.GIT_COMMAND,
            payload={
                "target_branch": target_branch,
                "task_branches": task_branches,
                "post_merge_agents": list(config.post_merge_agents),
            },
            purpose="Promote PR_READY branches into the configured target branch and validate the release.",
            risk_level="high",
            status=ActionApprovalStatus.PENDING,
            idempotency_key=key,
        )
        return await self.uow.safety.create_approval(approval)

    def _approval_key(self, config: ReleaseConfig, task_branches: list[str]) -> str:
        raw = "|".join(
            [str(self.run_id), config.target_branch or "", *sorted(task_branches)]
        )
        return "release-promotion:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    async def _merge_and_validate(
        self,
        run: domain.Run,
        project: domain.Project,
        config: ReleaseConfig,
        plan: ReleasePromotionPlan,
        *,
        run_tasks: list[domain.Task],
        approval_granted: bool,
    ) -> ReleasePromotionResult:
        assert self.uow.executions is not None
        release = self._release_metadata(run)
        release.update(
            {
                "state": ReleasePromotionState.MERGING.value,
                "target_branch": plan.target_branch,
                "task_branches": list(plan.task_branches),
                "approval_granted": approval_granted,
                "post_merge_agents": list(plan.post_merge_agents),
                "merged_branches": list(release.get("merged_branches") or []),
                "operational_profiles": profile_manifest(config.operational_profiles),
            }
        )
        run.resource_limits = dict(run.resource_limits or {})
        run.resource_limits[RELEASE_METADATA_KEY] = release
        await self.uow.executions.update_run(run)
        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            run_mode=RunMode.UNATTENDED,
            repository_root=project.root_path,
        )

        if config.require_release_tree_audit:
            audit = ReleaseTreeAuditor(Path(project.root_path)).audit()
            release["release_tree_audit"] = audit.model_dump(mode="json")
            run.resource_limits[RELEASE_METADATA_KEY] = release
            await self.uow.executions.update_run(run)
            if not audit.passed:
                return await self._block(
                    run,
                    "Release tree audit failed: " + "; ".join(audit.findings),
                    release,
                )

        if config.require_semantic_review:
            review = await self._run_semantic_review(
                project=project,
                plan=plan,
                run_tasks=run_tasks,
                git=git,
            )
            release["semantic_review"] = review
            run.resource_limits[RELEASE_METADATA_KEY] = release
            await self.uow.executions.update_run(run)
            if review.get("approved") is not True:
                return await self._block(
                    run,
                    "Chief Engineer semantic release review did not approve the merge.",
                    release,
                )

        try:
            for branch in plan.task_branches:
                if branch == plan.target_branch or branch in release["merged_branches"]:
                    continue
                if not await git.branch_exists(branch):
                    return await self._block(
                        run,
                        f"PR_READY branch does not exist locally: {branch}",
                        release,
                    )
                await git.merge_branch(branch)
                release["merged_branches"].append(branch)
                run.resource_limits[RELEASE_METADATA_KEY] = release
                await self.uow.executions.update_run(run)
        except Exception as exc:
            try:
                await git.merge_abort()
            except Exception:
                pass
            return await self._block(run, f"Merge failed safely: {str(exc)[:1000]}", release)

        merge_commit = await git.current_commit_hash()
        post_merge_results: list[dict[str, Any]] = []
        for agent in plan.post_merge_agents:
            normalized = agent.lower().replace("_", "").replace("-", "")
            if normalized == "tester":
                state = ReleasePromotionState.POST_MERGE_TESTING
                command = config.tester_command
                skill = "e2e-release-tester"
            elif normalized in {"safetyauditor", "securityauditor"}:
                state = ReleasePromotionState.POST_MERGE_SECURITY
                command = config.security_command
                skill = "security-auditor"
            else:
                return await self._block(run, f"Unsupported post-merge agent: {agent}", release)
            release["state"] = state.value
            run.resource_limits[RELEASE_METADATA_KEY] = release
            await self.uow.executions.update_run(run)
            try:
                exit_code, stdout, stderr = await self.command_runner(
                    project_id=self.project_id,
                    command=command,
                    uow=self.uow,
                    run_id=self.run_id,
                    task_id=None,
                    timeout=config.post_merge_timeout,
                    run_mode=RunMode.UNATTENDED,
                )
            except Exception as exc:
                exit_code, stdout, stderr = 1, "", str(exc)
            result = {
                "agent": agent,
                "skill": skill,
                "command": command,
                "status": "PASS" if exit_code == 0 else "FAIL",
                "exit_code": exit_code,
                "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-2000:],
            }
            post_merge_results.append(result)
            release["post_merge_results"] = post_merge_results
            run.resource_limits[RELEASE_METADATA_KEY] = release
            await self.uow.executions.update_run(run)
            if exit_code != 0:
                return await self._block(
                    run,
                    f"Post-merge {agent} failed with exit code {exit_code}.",
                    release,
                    post_merge_results=post_merge_results,
                    merge_commit=merge_commit,
                )

        release.update(
            {
                "state": ReleasePromotionState.COMPLETED.value,
                "merge_commit": merge_commit,
                "post_merge_results": post_merge_results,
            }
        )
        run.resource_limits[RELEASE_METADATA_KEY] = release
        run.summary = (
            f"Release promoted to {plan.target_branch} at {merge_commit}; "
            f"post-merge agents passed: {', '.join(plan.post_merge_agents)}."
        )
        await self.uow.executions.update_run(run)
        await self._audit(
            "release_promotion_completed",
            {"target_branch": plan.target_branch, "merge_commit": merge_commit},
        )
        return ReleasePromotionResult(
            state=ReleasePromotionState.COMPLETED,
            reason=run.summary,
            merge_commit=merge_commit,
            post_merge_results=post_merge_results,
        )

    async def _run_semantic_review(
        self,
        *,
        project: domain.Project,
        plan: ReleasePromotionPlan,
        run_tasks: list[domain.Task],
        git: GitAdapter,
    ) -> dict[str, Any]:
        """Run the optional semantic gate after deterministic evidence exists.

        This gate is opt-in and never replaces ContractVerifier, the mechanical
        pre-PR gate, Tester, or SafetyAuditor.  Failure is represented as a
        non-approval so full-access release remains fail-closed.
        """

        try:
            from localforge.chief_engineer.final_review import FinalReviewService
            from localforge.chief_engineer.service import ChiefEngineerService
            from localforge.core.config import load_config
            from localforge.llm.factory import build_chief_engineer_provider

            diffs: list[str] = []
            for branch in plan.task_branches:
                diff = await git.diff(f"{plan.target_branch}...{branch}")
                if diff.strip():
                    diffs.append(f"### {branch}\n{diff[:12000]}")
            contracts = [
                task.metadata.get("task_contract", {})
                for task in run_tasks
                if isinstance(task.metadata, dict)
            ]
            provider = build_chief_engineer_provider(load_config())
            review = await FinalReviewService(ChiefEngineerService(self.uow)).review_pr(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=None,
                provider=provider,
                model=load_config().chief_engineer.model or load_config().models.default_model,
                task_contract={"tasks": contracts},
                diff_summary="\n\n".join(diffs) or "No branch diff was available.",
                verifier_results={"all_tasks_ready": True, "task_count": len(run_tasks)},
                test_output_summary="All task-level PR_READY checks passed before release promotion.",
                risk_notes=["Optional semantic review requested by release policy."],
            )
            return review.model_dump(mode="json")
        except Exception as exc:
            return {
                "approved": False,
                "summary": "Semantic review could not be completed safely.",
                "required_changes": [],
                "risk_notes": [type(exc).__name__],
            }

    async def _block(
        self,
        run: domain.Run,
        reason: str,
        release: dict[str, Any],
        *,
        post_merge_results: list[dict[str, Any]] | None = None,
        merge_commit: str | None = None,
    ) -> ReleasePromotionResult:
        assert self.uow.executions is not None
        release.update(
            {
                "state": ReleasePromotionState.BLOCKED.value,
                "reason": reason,
                "post_merge_results": post_merge_results or release.get("post_merge_results", []),
            }
        )
        if merge_commit:
            release["merge_commit"] = merge_commit
        run.resource_limits = dict(run.resource_limits or {})
        run.resource_limits[RELEASE_METADATA_KEY] = release
        run.status = RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW
        run.summary = reason
        await self.uow.executions.update_run(run)
        await self._audit("release_promotion_blocked", {"reason": reason})
        return ReleasePromotionResult(
            state=ReleasePromotionState.BLOCKED,
            reason=reason,
            merge_commit=merge_commit,
            post_merge_results=post_merge_results or [],
        )

    @staticmethod
    def _release_metadata(run: domain.Run) -> dict[str, Any]:
        return dict((run.resource_limits or {}).get(RELEASE_METADATA_KEY) or {})

    async def _record_release_state(
        self,
        run: domain.Run,
        *,
        state: ReleasePromotionState,
        reason: str,
        target_branch: str,
        task_branches: list[str],
        approval_id: int | None = None,
        approval_granted: bool = False,
    ) -> None:
        assert self.uow.executions is not None
        metadata = self._release_metadata(run)
        metadata.update(
            {
                "state": state.value,
                "reason": reason,
                "target_branch": target_branch,
                "task_branches": task_branches,
                "approval_id": approval_id,
                "approval_granted": approval_granted,
                "post_merge_agents": list(POST_MERGE_AGENT_ORDER),
            }
        )
        run.resource_limits = dict(run.resource_limits or {})
        run.resource_limits[RELEASE_METADATA_KEY] = metadata
        await self.uow.executions.update_run(run)
        await self._audit(
            "release_promotion_state",
            {"state": state.value, "reason": reason, "approval_id": approval_id},
        )

    async def _audit(self, action: str, payload: dict[str, Any]) -> None:
        if self.uow.audits is None:
            return
        await self.uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=self.project_id,
                run_id=self.run_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="release-promotion",
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={"action": action, **payload},
            )
        )
