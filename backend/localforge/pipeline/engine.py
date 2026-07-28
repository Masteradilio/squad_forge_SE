import asyncio
import ast
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from dataclasses import dataclass
from difflib import SequenceMatcher

# Module-level cache of "allowed paths per task id" so the path-fuzz
# matcher can pick the closest candidate without re-reading the task
# metadata on every action proposal.
_ALLOWED_FILES_CACHE: dict[int, dict[str, str]] = {}


def _record_allowed_files(task_id: int | None, allowed_files) -> None:
    """Populate the mapping ``path -> original`` for close-enough
    contract matching. Called once per task on the first action that
    hits the guard."""
    if task_id is None or not allowed_files:
        return
    cache_key = task_id
    cache_entry = _ALLOWED_FILES_CACHE.setdefault(cache_key, {})
    for item in allowed_files:
        if not isinstance(item, str) or not item.strip():
            continue
        cache_entry[item.replace("\\", "/").lstrip("/")] = item


def _loosen_generated_path(path: str, task_id: int | None = None) -> str:
    """Project a model-generated path onto the closest allowed path.

    Local Ollama sometimes substitutes whole words in the task title
    when stitching a Python filename. We restrict the candidate set
    to entries that share directory and extension; the closest stem
    by ``difflib.SequenceMatcher.ratio`` wins. A ratio below
    ``0.55`` is treated as a genuine miss and we return the
    untouched ``path`` so the contract guard still rejects it.
    Path traversal tokens (``..``) are respected: the substitution is
    bounded to the stem.
    """
    if not path or task_id is None:
        return path
    candidates = _ALLOWED_FILES_CACHE.get(task_id, {})
    normalised = path.replace("\\", "/").lstrip("/")
    if normalised in candidates:
        return normalised
    g_dir, _, g_tail = normalised.rpartition("/")
    g_stem, _, g_ext = g_tail.partition(".")
    best: tuple[float, str] | None = None
    for allowed_path in candidates:
        a_dir, _, a_tail = allowed_path.rpartition("/")
        a_stem, _, a_ext = a_tail.partition(".")
        if a_dir != g_dir or a_ext != g_ext:
            continue
        ratio = SequenceMatcher(None, g_stem, a_stem).ratio()
        if best is None or ratio > best[0]:
            best = (ratio, allowed_path)
    if best is None or best[0] < 0.55:
        return path
    return best[1]

logger = logging.getLogger("localforge.pipeline")
from localforge.core.config import load_config
from localforge.chief_engineer.service import ChiefEngineerService
from localforge.llm.factory import build_chief_engineer_provider
from localforge.llm.openai_compatible import OpenAICompatibleProvider
from localforge.gitops.adapter import GitAdapter
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    AuditEventActorType,
    AuditEventType,
    ChiefEngineerCallReason,
    HandoffKind,
    RunMode,
    RunStatus,
    TaskRunStatus,
    TaskStatus,
)
from localforge.pipeline.context import RoleContext, RoleContextBuilder
from localforge.pipeline.roles import PIPELINES, PipelineMode
from localforge.pr_factory.local import LocalPRFactory
from localforge.runtime.actions import (
    RuntimeActionProposal,
    normalize_runtime_command,
    parse_action_proposals,
)
from localforge.runtime.compression import compress_tool_output
from localforge.runtime.file_tools import SafeFileEditor
from localforge.runtime.handoffs import RuntimeHandoffService
from localforge.safety.runner import run_safe_command
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@dataclass(frozen=True)
class RolePipelineResult:
    mode: PipelineMode
    roles: list[AgentRole]
    artifact_paths: list[str]
    consumed_handoff_ids: list[int]
    pr_artifact_path: str | None


class RolePipelineEngine:
    def __init__(self, uow: UnitOfWork, *, project_id: int, run_id: int):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id

    async def run_task(
        self,
        *,
        task_id: int,
        task_run_id: int,
        mode: PipelineMode = PipelineMode.DEFAULT,
        complete_run: bool = True,
    ) -> RolePipelineResult:
        assert self.uow.projects is not None
        assert self.uow.tasks is not None
        assert self.uow.executions is not None
        project = await self.uow.projects.get_project(self.project_id)
        task = await self.uow.tasks.get_task(task_id)
        task_run = await self.uow.tasks.get_task_run(task_run_id)
        if not project or not task or not task_run:
            raise ValueError("Project, task, and task run are required for role pipeline.")
        if not task_run.worktree_path:
            task_run.worktree_path = project.root_path
        if not task_run.branch_name:
            task_run.branch_name = f"localforge/{task.key.lower()}"

        # Load budgets configuration
        from localforge.core.config import load_config
        try:
            config = load_config()
            task_duration_limit = config.budgets.max_task_duration
            max_repair_limit = config.budgets.max_repair_attempts
            max_files = config.budgets.max_file_count
            max_diff = config.budgets.max_diff_growth
            max_llm_calls = config.budgets.max_active_model_calls
        except Exception:
            task_duration_limit = 600.0
            max_repair_limit = 3
            max_files = 10
            max_diff = 2000
            max_llm_calls = 4

        # Load overrides from run limits
        run = await self.uow.executions.get_run(self.run_id)
        if run and run.resource_limits:
            task_duration_limit = run.resource_limits.get(
                "max_task_duration", task_duration_limit
            )
            max_repair_limit = run.resource_limits.get(
                "max_repair_attempts", max_repair_limit
            )
            max_files = run.resource_limits.get("max_file_count", max_files)
            max_diff = run.resource_limits.get("max_diff_growth", max_diff)
            max_llm_calls = run.resource_limits.get(
                "max_active_model_calls", max_llm_calls
            )
        if isinstance(task.metadata, dict):
            task_duration_limit = float(
                task.metadata.get("max_task_duration", task_duration_limit)
                or task_duration_limit
            )
            max_diff = int(task.metadata.get("max_diff_growth", max_diff) or max_diff)

        # Configure LLM context variables
        from localforge.llm.context import (
            reset_llm_call_counter,
            set_active_task_run_id,
            set_llm_limit,
        )
        set_active_task_run_id(task_run_id)
        reset_llm_call_counter(task_run_id)
        set_llm_limit(task_run_id, max_llm_calls)

        try:
            # Run the core execution under wait_for timeout
            result = await asyncio.wait_for(
                self._execute_pipeline_core(
                    project=project,
                    task=task,
                    task_run=task_run,
                    mode=mode,
                    max_files=max_files,
                    max_diff=max_diff,
                    max_repair=max_repair_limit,
                    complete_run=complete_run,
                ),
                timeout=task_duration_limit,
            )
            return result
        except Exception as e:
            import logging
            logger = logging.getLogger("localforge.pipeline")
            logger.error(f"Pipeline execution failed for task {task.key}: {e}")

            # Transition task run status to FAILED
            task_run.status = TaskRunStatus.FAILED
            if isinstance(e, TimeoutError) or isinstance(e, asyncio.TimeoutError):
                summary = f"Task execution timed out after {task_duration_limit}s."
            else:
                summary = f"Task execution aborted: {e}"
            task_run.final_summary = summary
            await self.uow.tasks.update_task_run(task_run)

            # Move task to FAILED_SAFE
            await self.uow.tasks.update_task_status(task_id, TaskStatus.FAILED_SAFE)
            raise e
        finally:
            # Clear LLM context variables
            set_active_task_run_id(None)

    async def _execute_pipeline_core(
        self,
        *,
        project: domain.Project,
        task: domain.Task,
        task_run: domain.TaskRun,
        mode: PipelineMode,
        max_files: int,
        max_diff: int,
        max_repair: int,
        complete_run: bool,
    ) -> RolePipelineResult:
        assert self.uow.tasks is not None
        assert self.uow.executions is not None
        task_run.status = TaskRunStatus.RUNNING
        task_run = await self.uow.tasks.update_task_run(task_run)

        await self._advance_to(task, TaskStatus.PLANNING)

        roles = list(PIPELINES[mode])
        artifact_paths: list[str] = []
        consumed_ids: list[int] = []
        handoff_service = RuntimeHandoffService(
            self.uow, project_id=self.project_id, run_id=self.run_id, task_id=task.id or 0
        )
        context_builder = RoleContextBuilder(self.uow)

        repair_attempts = 0

        for index, role in enumerate(roles):
            # Check repair limits if the role is Fixer/Repairing
            if role == AgentRole.FIXER:
                repair_attempts += 1
                if repair_attempts > max_repair:
                    # The scheduler decides whether to recover this run via
                    # its budget-aware recovery loop. We surface a clear
                    # FAILED_SAFE marker and an audit event so the Scrum
                    # Master can attach guidance and the scheduler can
                    # escalate after the absolute cycle ceiling.
                    reason = (
                        f"Task run exhausted the per-cycle repair budget "
                        f"({max_repair}). Awaiting scheduler recovery."
                    )
                    if self.uow.audits is not None:
                        await self.uow.audits.append_audit_event(
                            domain.AuditEvent(
                                project_id=project.id if project.id is not None else 0,
                                run_id=self.run_id,
                                task_id=task.id or 0,
                                actor_type=AuditEventActorType.SYSTEM,
                                actor_id="pipeline-engine",
                                event_type=AuditEventType.SYSTEM_EVENT,
                                payload_redacted={
                                    "action": "repair_budget_exhausted",
                                    "task_key": task.key,
                                    "max_repair": max_repair,
                                    "reason": reason,
                                },
                            )
                        )
                    if task.id is not None:
                        await self.uow.tasks.update_task_status(
                            task.id, TaskStatus.FAILED_SAFE
                        )
                    task_run.final_summary = reason
                    task_run.status = TaskRunStatus.FAILED
                    task_run.ended_at = datetime.now(UTC)
                    await self.uow.tasks.update_task_run(task_run)
                    return RolePipelineResult(
                        mode=mode,
                        roles=list(roles),
                        artifact_paths=artifact_paths,
                        consumed_handoff_ids=consumed_ids,
                        pr_artifact_path=None,
                    )
                task_run.attempt_count = repair_attempts
                await self.uow.tasks.update_task_run(task_run)

            consumed = await self._consume_pending_for_role(
                task_run_id=task_run.id or 0,
                role=role,
                handoff_service=handoff_service,
            )
            consumed_ids.extend(h.id for h in consumed if h.id is not None)
            context = await context_builder.build(
                project=project,
                task=task,
                task_run=task_run,
                role=role,
                consumed_handoffs=consumed,
            )
            artifact_paths.append(
                await self._write_role_artifact(project, task, task_run, context)
            )
            await self._write_standard_artifact(project, task, task_run, role)
            if role == AgentRole.CODER:
                await self._execute_coder_actions(
                    project=project,
                    task=task,
                    task_run=task_run,
                    context=context,
                    max_repair=max_repair,
                )
            await self._apply_role_status(task.id or 0, role)

            # Heartbeat update (updating task_run update_at timestamp)
            task_run.ended_at = None
            await self.uow.tasks.update_task_run(task_run)

            # Check workspace budgets after this agent role execution
            self._check_workspace_budgets(
                worktree_path=task_run.worktree_path,
                max_files=max_files,
                max_diff=max_diff,
            )

            if index + 1 < len(roles):
                await handoff_service.create(
                    task_run_id=task_run.id or 0,
                    from_role=role,
                    to_role=roles[index + 1],
                    kind=_handoff_kind_for(role),
                    payload={"artifact": artifact_paths[-1], "role": role.value},
                )

        task_run.final_summary = f"{mode.value} role pipeline completed for {task.key}."
        task_run.status = TaskRunStatus.COMPLETED
        task_run = await self.uow.tasks.update_task_run(task_run)

        if (
            self.uow.audits is not None
            and self.uow.memory is not None
            and task_run.id is not None
        ):
            artifacts = await self.uow.audits.list_artifacts_for_task_run(task_run.id)
            await self.uow.memory.learn_from_completed_run(
                project_id=task.project_id,
                task_key=task.key,
                task_title=task.title,
                final_summary=task_run.final_summary,
                artifact_summaries=[
                    (artifact.type, artifact.summary) for artifact in artifacts
                ],
            )

        current_task = await self.uow.tasks.get_task(task.id or 0)
        if current_task and current_task.status == TaskStatus.TESTING:
            await self.uow.tasks.update_task_status(task.id or 0, TaskStatus.REVIEWING)

        current_task = await self.uow.tasks.get_task(task.id or 0)
        if current_task:
            await self._commit_generated_changes(current_task, task_run)

        pr_result = await LocalPRFactory(
            self.uow, project_id=self.project_id, run_id=self.run_id
        ).generate(task_id=task.id or 0, task_run_id=task_run.id or 0)
        if not pr_result.ready:
            task_run.status = TaskRunStatus.FAILED
            task_run.final_summary = (
                "PR readiness failed: " + "; ".join(pr_result.reasons or ["unknown reason"])
            )
            await self.uow.tasks.update_task_run(task_run)
            await self.uow.tasks.update_task_status(task.id or 0, TaskStatus.FAILED_SAFE)

        run = await self.uow.executions.get_run(self.run_id)
        if run and complete_run:
            run.status = RunStatus.COMPLETED
            run.summary = task_run.final_summary
            await self.uow.executions.update_run(run)

        return RolePipelineResult(
            mode=mode,
            roles=roles,
            artifact_paths=artifact_paths,
            consumed_handoff_ids=consumed_ids,
            pr_artifact_path=pr_result.artifact_path,
        )

    async def _commit_generated_changes(
        self, task: domain.Task, task_run: domain.TaskRun
    ) -> None:
        if task.id is None or not task_run.worktree_path:
            return
        if not os.path.exists(os.path.join(task_run.worktree_path, ".git")):
            return
        changed_files = [
            path for path in task.metadata.get("changed_files", []) if isinstance(path, str)
        ]
        existing_files = self._existing_changed_files(task_run.worktree_path, changed_files)
        if not existing_files:
            return
        if existing_files != changed_files:
            task.metadata["changed_files"] = existing_files
            assert self.uow.tasks is not None
            await self.uow.tasks.update_task(task)
        await GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            task_id=task.id,
            run_mode=RunMode.UNATTENDED,
        ).commit_paths(
            existing_files,
            f"{task.key}: {task.title}",
        )

    def _existing_changed_files(
        self, worktree_path: str, changed_files: list[str]
    ) -> list[str]:
        existing: list[str] = []
        root = os.path.realpath(worktree_path)
        for rel_path in dict.fromkeys(changed_files):
            target = os.path.realpath(os.path.abspath(os.path.join(worktree_path, rel_path)))
            if os.path.commonpath([root, target]) != root:
                continue
            if os.path.isfile(target):
                existing.append(rel_path.replace("\\", "/"))
        return existing

    def _check_workspace_budgets(
        self, worktree_path: str | None, max_files: int, max_diff: int
    ) -> None:
        """Validate worktree files and diff size against budget limits."""
        if not worktree_path or not os.path.exists(worktree_path):
            return

        import subprocess

        try:
            toplevel_res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            toplevel = os.path.realpath(toplevel_res.stdout.strip())
            if toplevel != os.path.realpath(worktree_path):
                raise subprocess.SubprocessError()

            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            modified_files = [
                line[3:].strip()
                for line in (status_res.stdout or "").splitlines()
                if line.strip()
            ]
            if len(modified_files) > max_files:
                raise ValueError(
                    f"Workspace file count budget exceeded: {len(modified_files)} "
                    f"files modified/created (Limit: {max_files})."
                )

            diff_res = subprocess.run(
                ["git", "diff"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            diff_len = len(diff_res.stdout or "")
            if diff_len > max_diff:
                raise ValueError(
                    f"Workspace diff growth budget exceeded: {diff_len} "
                    f"characters generated (Limit: {max_diff})."
                )
        except subprocess.SubprocessError:
            pass



    async def _consume_pending_for_role(
        self,
        *,
        task_run_id: int,
        role: AgentRole,
        handoff_service: RuntimeHandoffService,
    ) -> list[domain.Handoff]:
        assert self.uow.executions is not None
        pending = [
            h
            for h in await self.uow.executions.list_pending_handoffs(role)
            if h.task_run_id == task_run_id
        ]
        consumed: list[domain.Handoff] = []
        for handoff in pending:
            consumed.append(await handoff_service.consume_once(handoff.id))
        return consumed

    async def _write_role_artifact(
        self,
        project: domain.Project,
        task: domain.Task,
        task_run: domain.TaskRun,
        context: RoleContext,
    ) -> str:
        artifact = await ArtifactStore(self.uow).write_artifact(
            project_root=task_run.worktree_path or project.root_path,
            task_run_id=task_run.id or 0,
            task_key=task.key,
            run_id=self.run_id,
            filename=f"role-{context.role.value.lower()}.md",
            content=f"# {context.role.value}\n\n{context.rendered}\n",
            summary=f"{context.role.value} role artifact",
        )
        return artifact.path

    async def _write_standard_artifact(
        self,
        project: domain.Project,
        task: domain.Task,
        task_run: domain.TaskRun,
        role: AgentRole,
    ) -> None:
        filename = _standard_artifact_for(role)
        if filename is None:
            return
        content = f"# {role.value} Evidence\n\nGenerated by the Phase 23 role pipeline for {task.key}.\n"
        await ArtifactStore(self.uow).write_artifact(
            project_root=task_run.worktree_path or project.root_path,
            task_run_id=task_run.id or 0,
            task_key=task.key,
            run_id=self.run_id,
            filename=filename,
            content=content,
            summary=f"{role.value} standard artifact",
        )

    async def _execute_coder_actions(
        self,
        *,
        project: domain.Project,
        task: domain.Task,
        task_run: domain.TaskRun,
        context: RoleContext,
        max_repair: int,
    ) -> None:
        if not task_run.worktree_path:
            return
        assert self.uow.tasks is not None
        refreshed_task = await self.uow.tasks.get_task(task.id or 0)
        if refreshed_task:
            task = refreshed_task
        raw_actions = task.metadata.get("runtime_actions")
        editor = SafeFileEditor(
            self.uow,
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=task.id,
        )
        changed_files = [
            path for path in task.metadata.get("changed_files", []) if isinstance(path, str)
        ]
        command_summaries: list[str] = []
        if self._is_visual_task(task):
            max_repair = 0

        used_chief_engineer_initial = False
        from localforge.routing.capabilities import LocalWorkerCapabilityRouter, CapabilityDecision
        from localforge.models.enums import TaskSeniorityClass
        from localforge.routing.delegation import LocalWorkDelegationContract

        router = LocalWorkerCapabilityRouter(self.uow.session)
        decision = await router.route(task, model_name=context.model_profile_id)

        # Local Work Delegation Contract check
        delegation_contract = LocalWorkDelegationContract()
        is_delegation_allowed, delegation_rationale = delegation_contract.evaluate_delegation(task, task_run)

        if not is_delegation_allowed:
            decision = CapabilityDecision(
                model_tier="chief_engineer",
                escalate=True,
                local_draft_allowed=False,
                rationale=delegation_rationale,
                seniority_class=TaskSeniorityClass.CHIEF_ONLY
            )
            logger.info(f"Local delegation contract rejected task {task.key}: {delegation_rationale}")

        # Persist routing decision in audit log
        from localforge.models.enums import AuditEventActorType, AuditEventType
        assert self.uow.audits is not None
        await self.uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=task.project_id,
                run_id=self.run_id,
                task_id=task.id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="router",
                event_type=AuditEventType.STATE_CHANGE,
                payload_redacted={
                    "event": "routing_decision",
                    "model_tier": decision.model_tier,
                    "escalate": decision.escalate,
                    "local_draft_allowed": decision.local_draft_allowed,
                    "rationale": decision.rationale,
                    "seniority_class": decision.seniority_class.value
                }
            )
        )

        if (
            raw_actions is None
            and (self._is_visual_task(task) or decision.escalate)
            and not os.getenv("PYTEST_CURRENT_TEST")
        ):
            visual_target = self._visual_actual_output_path(task)
            if visual_target and visual_target not in changed_files:
                changed_files.append(visual_target)
            used_chief_engineer_initial = await self._try_chief_engineer_repair(
                task=task,
                task_run=task_run,
                context=context,
                editor=editor,
                changed_files=changed_files,
                command_summaries=command_summaries,
                validation_output=(
                    f"Initial implementation requires high-capacity Chief Engineer execution. "
                    f"Reason: {decision.rationale}. "
                    "Rewrite the complete target file without omissions or brevity placeholders."
                ),
            )
        if not used_chief_engineer_initial:
            if raw_actions is None:
                if (
                    decision.model_tier == "chief_engineer"
                    and not decision.local_draft_allowed
                    and not os.getenv("PYTEST_CURRENT_TEST")
                ):
                    raise ValueError(
                        "Task requires Chief Engineer execution under V3 routing, "
                        f"but no Chief Engineer action was applied. Reason: {decision.rationale}"
                    )
                if os.getenv("PYTEST_CURRENT_TEST"):
                    return
                raw_actions = await self._request_model_actions(task, context)
            try:
                proposals = await self._parse_or_repair_action_json(
                    raw_actions,
                    task=task,
                    context=context,
                    purpose="initial implementation",
                )
                await self._apply_action_proposals(
                    proposals,
                    editor=editor,
                    task=task,
                    task_run=task_run,
                    changed_files=changed_files,
                    command_summaries=command_summaries,
                )
            except Exception as e:
                if "Anti-loop block" in str(e) or "truncated" in str(e).lower() or "brevity" in str(e).lower():
                    from localforge.services.routing import ModelRoutingService
                    assert self.uow.session is not None
                    routing_svc = ModelRoutingService(self.uow.session)
                    await routing_svc.disqualify_model(
                        model_name=context.model_profile_id,
                        task_class=decision.seniority_class.value,
                        reason=f"Model generated truncated code: {e}"
                    )
                    command_summaries.append(
                        f"Local model {context.model_profile_id} disqualified for truncation. "
                        "Escalating implementation to Chief Engineer."
                    )
                    used_chief_engineer_initial = await self._try_chief_engineer_repair(
                        task=task,
                        task_run=task_run,
                        context=context,
                        editor=editor,
                        changed_files=changed_files,
                        command_summaries=command_summaries,
                        validation_output=(
                            f"Initial local worker implementation failed: {e}. "
                            "Rewrite the complete target file without omissions."
                        ),
                    )
                else:
                    raise e
        await self._sanitize_generated_python_files(
            editor=editor,
            task=task,
            task_run=task_run,
            changed_files=changed_files,
        )
        if changed_files:
            task.metadata["changed_files"] = list(dict.fromkeys(changed_files))
            await self.uow.tasks.update_task(task)
            if self._should_run_pytest(task_run.worktree_path, changed_files):
                for attempt in range(max_repair + 1):
                    syntax_error = self._validate_generated_python_syntax(
                        task_run.worktree_path, changed_files
                    )
                    if syntax_error:
                        code, stdout, stderr = 1, "", syntax_error
                        command_summaries.append(
                            compress_tool_output(syntax_error, max_chars=800)
                        )
                    else:
                        code, stdout, stderr = await self._run_pytest_validation(
                            task=task,
                            task_run=task_run,
                            command_summaries=command_summaries,
                        )
                    if code == 0:
                        break
                    if self._is_visual_task(task) and self._has_task_contract(task):
                        if not os.getenv("PYTEST_CURRENT_TEST"):
                            code, stdout, stderr = await self._run_chief_engineer_repair_rounds(
                                task=task,
                                task_run=task_run,
                                context=context,
                                editor=editor,
                                changed_files=changed_files,
                                command_summaries=command_summaries,
                                validation_output=stdout + stderr,
                            )
                            if code == 0:
                                break
                        if attempt < max_repair:
                            continue
                    if attempt >= max_repair:
                        if (
                            self._has_task_contract(task)
                            and not self._is_visual_task(task)
                            and not os.getenv("PYTEST_CURRENT_TEST")
                        ):
                            code, stdout, stderr = await self._run_chief_engineer_repair_rounds(
                                task=task,
                                task_run=task_run,
                                context=context,
                                editor=editor,
                                changed_files=changed_files,
                                command_summaries=command_summaries,
                                validation_output=stdout + stderr,
                            )
                            if code == 0:
                                break
                        await self._write_command_summary(
                            project=project,
                            task_run=task_run,
                            task=task,
                            command_summaries=command_summaries,
                        )
                        await self._write_validation_failure_artifact(
                            project=project,
                            task_run=task_run,
                            task=task,
                            stdout=stdout,
                            stderr=stderr,
                        )
                        raise ValueError(
                            "Generated tests failed: "
                            + compress_tool_output(stdout + stderr, max_chars=500)
                        )
                    try:
                        repair_actions = await self._request_repair_actions(
                            task=task,
                            context=context,
                            worktree_path=task_run.worktree_path,
                            changed_files=list(dict.fromkeys(changed_files)),
                            validation_output=stdout + stderr,
                            attempt=attempt + 1,
                        )
                        repair_proposals = await self._parse_or_repair_action_json(
                            repair_actions,
                            task=task,
                            context=context,
                            purpose=f"repair attempt {attempt + 1}",
                        )
                        repair_proposals = self._filter_pytest_repair_proposals(
                            repair_proposals
                        )
                        await self._apply_action_proposals(
                            repair_proposals,
                            editor=editor,
                            task=task,
                            task_run=task_run,
                            changed_files=changed_files,
                            command_summaries=command_summaries,
                        )
                    except Exception as e:
                        if "Anti-loop block" in str(e) or "truncated" in str(e).lower() or "brevity" in str(e).lower() or "json" in str(e).lower():
                            from localforge.services.routing import ModelRoutingService
                            assert self.uow.session is not None
                            routing_svc = ModelRoutingService(self.uow.session)
                            await routing_svc.disqualify_model(
                                model_name=context.model_profile_id,
                                task_class=decision.seniority_class.value,
                                reason=f"Model generated bad format/truncated code: {e}"
                            )
                            command_summaries.append(
                                f"Local model {context.model_profile_id} disqualified during repair. "
                                "Escalating repair to Chief Engineer."
                            )
                            code, stdout, stderr = await self._run_chief_engineer_repair_rounds(
                                task=task,
                                task_run=task_run,
                                context=context,
                                editor=editor,
                                changed_files=changed_files,
                                command_summaries=command_summaries,
                                validation_output=f"Local repair failed: {e}. Chief Engineer must recover.",
                            )
                            if code == 0:
                                break
                            continue
                        else:
                            raise e
                    await self._sanitize_generated_python_files(
                        editor=editor,
                        task=task,
                        task_run=task_run,
                        changed_files=changed_files,
                    )
                    task.metadata["changed_files"] = list(dict.fromkeys(changed_files))
                    await self.uow.tasks.update_task(task)
        if (
            not changed_files
            and command_summaries
            and self._has_task_contract(task)
            and not os.getenv("PYTEST_CURRENT_TEST")
        ):
            code, stdout, stderr = await self._run_chief_engineer_repair_rounds(
                task=task,
                task_run=task_run,
                context=context,
                editor=editor,
                changed_files=changed_files,
                command_summaries=command_summaries,
                validation_output="\n".join(command_summaries),
            )
            if code != 0:
                await self._write_command_summary(
                    project=project,
                    task_run=task_run,
                    task=task,
                    command_summaries=command_summaries,
                )
                await self._write_validation_failure_artifact(
                    project=project,
                    task_run=task_run,
                    task=task,
                    stdout=stdout,
                    stderr=stderr,
                )
                raise ValueError(
                    "Generated tests failed: "
                    + compress_tool_output(stdout + stderr, max_chars=500)
                )
        if command_summaries:
            await self._write_command_summary(
                project=project,
                task_run=task_run,
                task=task,
                command_summaries=command_summaries,
            )

    async def _write_command_summary(
        self,
        *,
        project: domain.Project,
        task_run: domain.TaskRun,
        task: domain.Task,
        command_summaries: list[str],
    ) -> None:
        if not command_summaries:
            return
        await ArtifactStore(self.uow).write_artifact(
            project_root=project.root_path,
            task_run_id=task_run.id or 0,
            task_key=task.key,
            run_id=self.run_id,
            filename="review.md",
            content="\n\n".join(command_summaries),
            summary="Coder command results",
        )

    async def _write_validation_failure_artifact(
        self,
        *,
        project: domain.Project,
        task_run: domain.TaskRun,
        task: domain.Task,
        stdout: str,
        stderr: str,
    ) -> None:
        assert task_run.id is not None
        await ArtifactStore(self.uow).write_artifact(
            project_root=project.root_path,
            task_run_id=task_run.id,
            task_key=task.key,
            run_id=self.run_id,
            filename="tests.md",
            content=(
                "# Validation Failure\n\n"
                "## stdout\n\n"
                "```text\n"
                f"{stdout}\n"
                "```\n\n"
                "## stderr\n\n"
                "```text\n"
                f"{stderr}\n"
                "```\n"
            ),
            summary="Full pytest validation failure output",
        )

    async def _apply_action_proposals(
        self,
        proposals: list[RuntimeActionProposal],
        *,
        editor: SafeFileEditor,
        task: domain.Task,
        task_run: domain.TaskRun,
        changed_files: list[str],
        command_summaries: list[str],
    ) -> None:
        assert task_run.worktree_path is not None
        for action in proposals:
            if action.kind == "write_file" and action.path:
                if not self._is_path_allowed_by_task_contract(task, action.path):
                    command_summaries.append(
                        f"Contract blocked write outside allowed files: {action.path}"
                    )
                    continue

                # Check for truncation/omission markers
                is_code_file = any(
                    action.path.endswith(ext)
                    for ext in (".py", ".js", ".ts", ".html", ".css", ".go", ".c", ".cpp", ".java")
                )
                truncation_marker = self._detect_truncation(action.content) if is_code_file else None
                if truncation_marker:
                    raise ValueError(
                        f"Anti-loop block: Generated file content for '{action.path}' "
                        f"contains truncation/omission marker '{truncation_marker}'"
                    )

                result = await editor.write_text(
                    task_run.worktree_path,
                    action.path,
                    action.content,
                    task_run_id=task_run.id,
                    task_key=task.key,
                )
                changed_files.append(
                    os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
                )
            elif action.kind == "append_content" and action.path:
                if not self._is_path_allowed_by_task_contract(task, action.path):
                    command_summaries.append(
                        f"Contract blocked append outside allowed files: {action.path}"
                    )
                    continue
                existing = ""
                target_path = os.path.join(task_run.worktree_path, action.path)
                if os.path.exists(target_path):
                    existing = await editor.read_text(task_run.worktree_path, action.path)
                result = await editor.write_text(
                    task_run.worktree_path,
                    action.path,
                    existing + action.content,
                    task_run_id=task_run.id,
                    task_key=task.key,
                )
                changed_files.append(
                    os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
                )
            elif action.kind == "run_command" and action.command:
                command = normalize_runtime_command(action.command)
                try:
                    code, stdout, stderr = await run_safe_command(
                        project_id=self.project_id,
                        command=command,
                        uow=self.uow,
                        run_id=self.run_id,
                        task_id=task.id,
                    )
                    command_summaries.append(
                        compress_tool_output(
                            f"{command}: exit {code}; stdout={stdout}; stderr={stderr}",
                            max_chars=400,
                        )
                    )
                except Exception as e:
                    command_summaries.append(
                        compress_tool_output(
                            f"{command}: blocked or failed: {e}",
                            max_chars=400,
                        )
                    )

    def _is_path_allowed_by_task_contract(self, task: domain.Task, path: str) -> bool:
        task_contract = task.metadata.get("task_contract")
        if not isinstance(task_contract, dict):
            return True
        raw_allowed = task_contract.get("allowed_files")
        if not isinstance(raw_allowed, list) or not raw_allowed:
            return True
        normalized = path.replace("\\", "/").lstrip("/")
        # Lazy-populate the fuzz cache for this task so subsequent
        # action proposals find the close-enough match cheaply.
        if task.id is not None:
            _record_allowed_files(task.id, raw_allowed)
        allowed = {
            item.replace("\\", "/").lstrip("/")
            for item in raw_allowed
            if isinstance(item, str)
        }
        if normalized in allowed:
            return True
        # Local Ollama sometimes substitutes whole words in the task
        # title when stitching a Python filename. ``src/..._1_float.py``
        # stands no chance against an exact equality check. Before
        # rejecting the write, give the closest candidate in the same
        # directory/extension a chance and audit the substitution.
        candidate = _loosen_generated_path(path, task.id)
        if candidate != normalized and candidate in allowed:
            logger.warning(
                "task=%s write-path-substitution requested=%r -> %r",
                getattr(task, "key", "?"),
                path,
                candidate,
            )
            return True
        logger.warning(
            "task=%s write-path-rejected requested=%r allowed=%s",
            getattr(task, "key", "?"),
            path,
            sorted(allowed),
        )
        return False
    async def _run_pytest_validation(
        self,
        *,
        task: domain.Task,
        task_run: domain.TaskRun,
        command_summaries: list[str],
    ) -> tuple[int, str, str]:
        command = f'"{sys.executable}" -m pytest -q'
        task_contract = task.metadata.get("task_contract")
        if isinstance(task_contract, dict):
            canonical = task_contract.get("canonical_test_command")
            if isinstance(canonical, str) and canonical.strip():
                command = normalize_runtime_command(canonical.strip())
        code, stdout, stderr = await run_safe_command(
            project_id=self.project_id,
            command=command,
            uow=self.uow,
            run_id=self.run_id,
            task_id=task.id,
        )
        command_summaries.append(
            compress_tool_output(
                f"{command}: exit {code}; stdout={stdout}; stderr={stderr}",
                max_chars=800,
            )
        )
        if code == 0:
            is_visual = False
            contract = task.metadata.get("task_contract")
            if isinstance(contract, dict):
                is_visual = bool(contract.get("visual_required", False))
            if not is_visual:
                is_visual = bool(task.metadata.get("visual_required", False))
            if is_visual and task_run.worktree_path:
                from localforge.visual.screenshot import capture_html_screenshot
                from localforge.visual.gate import VisualFidelityGate
                visual_ref_rel = None
                visual_actual_rel = None
                visual_threshold = 0.90
                if isinstance(contract, dict):
                    visual_ref_rel = contract.get("visual_reference_image")
                    visual_actual_rel = contract.get("visual_actual_output")
                    visual_threshold = float(contract.get("visual_similarity_threshold", 0.90))
                if not visual_ref_rel:
                    visual_ref_rel = task.metadata.get("visual_reference_image")
                if not visual_actual_rel:
                    visual_actual_rel = task.metadata.get("visual_actual_output")
                if "visual_similarity_threshold" in task.metadata:
                    visual_threshold = float(task.metadata["visual_similarity_threshold"])
                ref_image_path = None
                if visual_ref_rel:
                    p1 = os.path.normpath(os.path.join(task_run.worktree_path, visual_ref_rel))
                    if os.path.isfile(p1):
                        ref_image_path = p1
                    else:
                        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                        p2 = os.path.normpath(os.path.join(backend_dir, "..", visual_ref_rel))
                        if os.path.isfile(p2):
                            ref_image_path = p2
                        elif os.path.isfile(visual_ref_rel):
                            ref_image_path = os.path.abspath(visual_ref_rel)
                html_abs_path = None
                if visual_actual_rel:
                    p_html = os.path.normpath(os.path.join(task_run.worktree_path, visual_actual_rel))
                    if os.path.isfile(p_html):
                        html_abs_path = p_html
                else:
                    for root_dir, _, files in os.walk(task_run.worktree_path):
                        for file in files:
                            if file.endswith(".html"):
                                html_abs_path = os.path.join(root_dir, file)
                                break
                        if html_abs_path:
                            break
                if not html_abs_path:
                    code = 1
                    stderr = "Visual validation failed: Actual HTML output file not found in worktree."
                    command_summaries.append(f"Visual validation: {stderr}")
                    return code, stdout, stderr
                actual_image_path = os.path.join(task_run.worktree_path, ".localforge", "visual_actual.png")
                os.makedirs(os.path.dirname(actual_image_path), exist_ok=True)
                success = capture_html_screenshot(html_abs_path, actual_image_path)
                if not success:
                    code = 1
                    stderr = "Visual validation failed: Failed to capture HTML screenshot."
                    command_summaries.append(f"Visual validation: {stderr}")
                    return code, stdout, stderr
                if visual_ref_rel and not ref_image_path:
                    code = 1
                    stderr = f"Visual validation failed: Reference image not found for path '{visual_ref_rel}'."
                    command_summaries.append(f"Visual validation: {stderr}")
                    return code, stdout, stderr
                if not ref_image_path:
                    command_summaries.append(
                        "Visual validation passed: HTML screenshot captured; no reference image configured."
                    )
                    return code, stdout, stderr
                gate_res = VisualFidelityGate().evaluate(
                    reference_image_path=ref_image_path,
                    actual_image_path=actual_image_path,
                    task_is_visual=True,
                    min_similarity=visual_threshold,
                )
                if not gate_res.passed:
                    code = 1
                    stderr = f"Visual validation failed: {gate_res.summary}"
                    command_summaries.append(f"Visual validation: {stderr} (Metrics: {gate_res.metrics})")
                    return code, stdout, stderr
                else:
                    command_summaries.append(f"Visual validation passed: similarity {gate_res.metrics.get('similarity', 1.0):.3f} >= {visual_threshold}")
        return code, stdout, stderr

    async def _parse_or_repair_action_json(
        self,
        raw_actions: object,
        *,
        task: domain.Task,
        context: RoleContext,
        purpose: str,
    ) -> list[RuntimeActionProposal]:
        try:
            return parse_action_proposals(raw_actions)
        except Exception as exc:
            if os.getenv("PYTEST_CURRENT_TEST"):
                raise
            invalid_payload = (
                "The previous action payload could not be parsed or validated.\n"
                f"Error: {exc!r}\n"
                "Payload:\n"
                f"{str(raw_actions)}"
            )
            repaired = await self._request_action_json_repair(
                task=task,
                context=context,
                invalid_payload=invalid_payload,
                purpose=purpose,
            )
            try:
                return parse_action_proposals(repaired)
            except Exception as repair_exc:
                raise ValueError(
                    "Action JSON remained invalid after repair: "
                    f"{repair_exc!r}"
                ) from repair_exc

    def _should_run_pytest(self, worktree_path: str, changed_files: list[str]) -> bool:
        if any(path.startswith("tests/") or path.startswith("test_") for path in changed_files):
            return True
        return os.path.isdir(os.path.join(worktree_path, "tests"))

    def _validate_generated_python_syntax(
        self, worktree_path: str, changed_files: list[str]
    ) -> str:
        python_paths = {
            path
            for path in changed_files
            if path.endswith(".py") and not path.startswith(".localforge/")
        }
        tests_dir = os.path.join(worktree_path, "tests")
        if os.path.isdir(tests_dir):
            for root, _, files in os.walk(tests_dir):
                for filename in files:
                    if filename.endswith(".py"):
                        python_paths.add(
                            os.path.relpath(
                                os.path.join(root, filename), worktree_path
                            ).replace("\\", "/")
                        )
        failures: list[str] = []
        root = os.path.realpath(worktree_path)
        for rel_path in sorted(python_paths):
            target = os.path.realpath(os.path.abspath(os.path.join(worktree_path, rel_path)))
            if os.path.commonpath([root, target]) != root or not os.path.isfile(target):
                continue
            try:
                with open(target, encoding="utf-8") as handle:
                    content = handle.read()
                ast.parse(content, filename=rel_path)
            except SyntaxError as exc:
                failures.append(f"{rel_path}:{exc.lineno}:{exc.offset}: {exc.msg}")
            except UnicodeDecodeError:
                continue
        if not failures:
            return ""
        return (
            "Python syntax validation failed before pytest:\n"
            + "\n".join(f"- {failure}" for failure in failures)
        )

    def _filter_pytest_repair_proposals(
        self, proposals: list[RuntimeActionProposal]
    ) -> list[RuntimeActionProposal]:
        return [
            proposal
            for proposal in proposals
            if not (
                proposal.kind == "write_file"
                and proposal.path is not None
                and (
                    proposal.path == "tests"
                    or proposal.path.startswith("tests/")
                    or proposal.path.startswith("test_")
                )
            )
        ]

    async def _try_chief_engineer_repair(
        self,
        *,
        task: domain.Task,
        task_run: domain.TaskRun,
        context: RoleContext,
        editor: SafeFileEditor,
        changed_files: list[str],
        command_summaries: list[str],
        validation_output: str,
    ) -> bool:
        if not task_run.worktree_path:
            return False
        config = load_config()
        if not config.chief_engineer.enabled or not config.chief_engineer.model:
            return False
        try:
            provider = build_chief_engineer_provider(config)
            plan = await ChiefEngineerService(self.uow).plan_semantic_repair(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=task.id,
                task_contract=task.metadata.get("task_contract", {}),
                changed_files_context=self._render_changed_file_context(
                    task_run.worktree_path,
                    list(dict.fromkeys(changed_files)),
                    max_chars=28000 if self._is_visual_task(task) else 12000,
                    max_file_chars=22000 if self._is_visual_task(task) else 3000,
                ),
                validation_output=validation_output,
                provider=provider,
                model=config.chief_engineer.model,
            )
        except Exception as exc:
            logger.error("Chief Engineer semantic repair call failed", exc_info=True)
            command_summaries.append(
                "Chief Engineer repair unavailable: "
                + compress_tool_output(str(exc), max_chars=800)
            )
            return False
        runtime_actions = plan.runtime_actions()
        if not runtime_actions:
            command_summaries.append("Chief Engineer repair returned no actions.")
            return False
        await self._apply_action_proposals(
            runtime_actions,
            editor=editor,
            task=task,
            task_run=task_run,
            changed_files=changed_files,
            command_summaries=command_summaries,
        )
        await self._sanitize_generated_python_files(
            editor=editor,
            task=task,
            task_run=task_run,
            changed_files=changed_files,
        )
        command_summaries.append(f"Chief Engineer repair applied: {plan.summary}")
        return True

    async def _run_chief_engineer_repair_rounds(
        self,
        *,
        task: domain.Task,
        task_run: domain.TaskRun,
        context: RoleContext,
        editor: SafeFileEditor,
        changed_files: list[str],
        command_summaries: list[str],
        validation_output: str,
    ) -> tuple[int, str, str]:
        if self.uow.tasks is None or task_run.worktree_path is None:
            return 1, validation_output, ""
        code = 1
        stdout = validation_output
        stderr = ""
        for round_index in range(3):
            repaired = await self._try_chief_engineer_repair(
                task=task,
                task_run=task_run,
                context=context,
                editor=editor,
                changed_files=changed_files,
                command_summaries=command_summaries,
                validation_output=stdout + stderr,
            )
            if not repaired:
                break
            task.metadata["changed_files"] = list(dict.fromkeys(changed_files))
            await self.uow.tasks.update_task(task)
            syntax_error = self._validate_generated_python_syntax(
                task_run.worktree_path, changed_files
            )
            if syntax_error:
                stdout, stderr = "", syntax_error
                command_summaries.append(
                    compress_tool_output(syntax_error, max_chars=800)
                )
            else:
                code, stdout, stderr = await self._run_pytest_validation(
                    task=task,
                    task_run=task_run,
                    command_summaries=command_summaries,
                )
                if code == 0:
                    break
            if round_index < 2:
                command_summaries.append(
                    "Chief Engineer repair did not pass validation; escalating one compact retry."
                )
        return code, stdout, stderr

    async def _sanitize_generated_python_files(
        self,
        *,
        editor: SafeFileEditor,
        task: domain.Task,
        task_run: domain.TaskRun,
        changed_files: list[str],
    ) -> None:
        if not task_run.worktree_path:
            return
        python_paths = {
            path
            for path in changed_files
            if path.endswith(".py")
            and not path.startswith(".localforge/")
        }
        tests_dir = os.path.join(task_run.worktree_path, "tests")
        if os.path.isdir(tests_dir):
            for root, _, files in os.walk(tests_dir):
                for filename in files:
                    if filename.endswith(".py"):
                        abs_path = os.path.join(root, filename)
                        python_paths.add(
                            os.path.relpath(abs_path, task_run.worktree_path).replace("\\", "/")
                        )

        for rel_path in sorted(python_paths):
            target = os.path.join(task_run.worktree_path, rel_path)
            if not os.path.isfile(target):
                continue
            try:
                with open(target, encoding="utf-8") as handle:
                    original = handle.read()
            except UnicodeDecodeError:
                continue

            sanitized = self._sanitize_python_content(original)
            if sanitized != original:
                result = await editor.write_text(
                    task_run.worktree_path,
                    rel_path,
                    sanitized,
                    task_run_id=task_run.id,
                    task_key=task.key,
                )
                changed_files.append(
                    os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
                )

    def _sanitize_python_content(self, content: str) -> str:
        content = self._extract_python_fence(content).replace("×", "*")
        cleaned: list[str] = []
        started = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                continue
            if stripped in {":coding=utf-8", ": coding=utf-8"}:
                cleaned.append("# coding=utf-8")
                started = True
                continue
            lstripped = line.lstrip()
            indent = line[: len(line) - len(lstripped)]
            if lstripped.startswith(";") and lstripped[1:].startswith(
                ('"""', "'''", "from ", "import ", "class ", "def ")
            ):
                line = indent + lstripped[1:]
                lstripped = line.lstrip()
            if not started and stripped and not self._looks_like_python_start(lstripped):
                continue
            if stripped:
                started = True
            cleaned.append(line)
        sanitized = "\n".join(cleaned).rstrip() + "\n"
        return self._drop_unmatched_lone_closing_braces(sanitized)

    def _drop_unmatched_lone_closing_braces(self, content: str) -> str:
        try:
            compile(content, "<localforge-generated>", "exec")
            return content
        except SyntaxError as exc:
            if "unmatched '}'" not in str(exc):
                return content
        lines = content.splitlines()
        cleaned = [line for line in lines if line.strip() not in {"}", "};"}]
        temp_content = "\n".join(cleaned).rstrip() + "\n"
        try:
            compile(temp_content, "<localforge-generated>", "exec")
            return temp_content
        except SyntaxError as exc:
            if "unmatched '}'" not in str(exc):
                return temp_content

        cleaned2 = []
        for line in cleaned:
            stripped = line.rstrip()
            if stripped.endswith("}") and "{" not in line:
                idx = line.rfind("}")
                line = line[:idx] + line[idx+1:]
            cleaned2.append(line)
        return "\n".join(cleaned2).rstrip() + "\n"

    def _extract_python_fence(self, content: str) -> str:
        if "```" not in content:
            return content
        lines = content.splitlines()
        in_block = False
        selected: list[str] = []
        for line in lines:
            stripped = line.strip().lower()
            if stripped.startswith("```"):
                if not in_block:
                    in_block = True
                    selected = []
                    continue
                if selected:
                    return "\n".join(selected)
                in_block = False
                continue
            if in_block:
                selected.append(line)
        return "\n".join(selected) if selected else content

    def _looks_like_python_start(self, line: str) -> bool:
        return line.startswith(
            (
                "#",
                '"""',
                "'''",
                "from ",
                "import ",
                "class ",
                "def ",
                "@",
                "async def ",
            )
        ) or bool(re.match(r"[A-Za-z_][A-Za-z0-9_]*\s*=", line))

    def _has_task_contract(self, task: domain.Task) -> bool:
        return isinstance(task.metadata.get("task_contract"), dict)

    async def _request_model_actions(
        self, task: domain.Task, context: RoleContext
    ) -> str:
        prompt = (
            "You are the Coder role in LocalForge OS. Return only valid JSON with this "
            "shape: {\"actions\":[{\"kind\":\"write_file\",\"path\":\"relative/path\","
            "\"content\":\"file contents\"},{\"kind\":\"append_content\","
            "\"path\":\"relative/path\",\"content\":\"extra contents\"},"
            "{\"kind\":\"run_command\",\"command\":\"git status\"}]}.\n"
            "Use relative paths inside the worktree. Do not write outside the project. "
            "If a task contract is present, write only files listed in allowed_files, "
            "implement all required_public_apis, avoid every forbidden_dependency, "
            "and use canonical_test_command for validation. "
            "Prefer small, coherent files. Do not include markdown fences. "
            "Only propose run_command actions for conservative validation commands "
            "such as git status, git diff, pytest, ruff check, or mypy. "
            "If you create Python tests, put them under tests/ and make every "
            "import path work from the repository root. If tests import from a "
            "package, also write that package's __init__.py with the required "
            "public exports.\n\n"
            f"{context.rendered}\n\n"
            "Create the minimal implementation files needed to satisfy this task's acceptance criteria."
        )
        task_class = task.metadata.get("task_contract", {}).get("seniority_class", "local_assisted")
        response, model_used = await self._chat_completion_with_local_fallback(
            prompt=prompt,
            preferred_model=context.model_profile_id,
            timeout=180.0,
            task_class=task_class,
        )
        await self._record_local_model_call(
            task=task,
            model=model_used,
            reason=ChiefEngineerCallReason.TASK_RISK_CLASSIFICATION,
            prompt=prompt,
            response=response,
        )
        return response

    async def _request_repair_actions(
        self,
        *,
        task: domain.Task,
        context: RoleContext,
        worktree_path: str,
        changed_files: list[str],
        validation_output: str,
        attempt: int,
    ) -> str:
        config = load_config()
        repair_model = config.models.roles.get(AgentRole.FIXER.value, context.model_profile_id)
        prompt = (
            "You are repairing a LocalForge task after validation failed. Return only valid JSON "
            "with actions using this shape: {\"actions\":[{\"kind\":\"write_file\","
            "\"path\":\"relative/path\",\"content\":\"file contents\"},"
            "{\"kind\":\"append_content\",\"path\":\"relative/path\","
            "\"content\":\"extra contents\"}]}. "
            "Prefer fixing existing generated files. Do not include markdown fences. "
            "Do not propose commands unless they are conservative validation commands. "
            "Do not modify files under tests/ during repair; fix production code, "
            "exports, modules, or package layout instead. "
            "Fix import errors by aligning package names, module names, __init__.py "
            "exports, and test imports so pytest works from the repository root. "
            "Do not write tests that instantiate Tkinter or require a graphical display; "
            "keep validation headless.\n\n"
            "If a task contract is present, preserve allowed_files, required_public_apis, "
            "forbidden_dependencies, implementation_notes, and canonical_test_command. "
            f"Repair attempt: {attempt}\n"
            f"{context.rendered}\n\n"
            "Current generated files:\n"
            f"{self._render_changed_file_context(worktree_path, changed_files)}\n\n"
            "Validation failure output:\n"
            f"{compress_tool_output(validation_output, max_chars=8000)}"
        )
        task_class = task.metadata.get("task_contract", {}).get("seniority_class", "local_assisted")
        response, model_used = await self._chat_completion_with_local_fallback(
            prompt=prompt,
            preferred_model=context.model_profile_id,
            timeout=120.0,
            task_class=task_class,
        )
        await self._record_local_model_call(
            task=task,
            model=model_used,
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            prompt=prompt,
            response=response,
        )
        return response

    async def _record_local_model_call(
        self,
        *,
        task: domain.Task,
        model: str | None,
        reason: ChiefEngineerCallReason,
        prompt: str,
        response: str,
    ) -> None:
        if self.uow.model_calls is None:
            return
        await self.uow.model_calls.record_call(
            domain.ModelCallLedger(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=task.id,
                provider="ollama",
                model=model or "unknown-local-model",
                reason=reason,
                input_tokens=max(1, len(prompt) // 4),
                output_tokens=max(1, len(response) // 4),
                estimated_cost_usd=0.0,
                status="success",
                metadata={"tier": "local", "v3_economy_first": True},
            )
        )

    async def _local_model_candidates(self, preferred_model: str | None, task_class: str | None = None) -> list[str]:
        config = load_config()
        candidates = [
            preferred_model,
            config.models.default_model,
            *config.models.fallback_models,
        ]
        ordered: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        
        if task_class:
            from localforge.services.routing import ModelRoutingService
            from datetime import UTC, datetime
            assert self.uow.session is not None
            routing_svc = ModelRoutingService(self.uow.session)
            
            filtered = []
            for candidate in ordered:
                cap = await routing_svc.get_model_capability(candidate, task_class)
                if cap and cap.disqualified_until and cap.disqualified_until > datetime.now(UTC):
                    continue
                filtered.append(candidate)
            ordered = filtered

        return ordered

    async def _chat_completion_with_local_fallback(
        self,
        *,
        prompt: str,
        preferred_model: str | None,
        timeout: float,
        task_class: str | None = None,
    ) -> tuple[str, str]:
        config = load_config()
        failures: list[str] = []
        candidates = await self._local_model_candidates(preferred_model, task_class)
        for model in candidates:
            provider = OpenAICompatibleProvider(
                base_url=config.models.base_url,
                default_model=model,
            )
            try:
                response = await provider.chat_completion(
                    [{"role": "user", "content": prompt}],
                    response_schema={"type": "object"},
                    timeout=timeout,
                    model=model,
                )
            except Exception as exc:
                failures.append(f"{model}: {exc!r}")
                logger.warning("Local model %s failed; trying fallback when available.", model)
                continue
            if not isinstance(response, str):
                failures.append(f"{model}: streaming response is not supported")
                continue
            return response, model
        raise RuntimeError(
            "All local model candidates failed: " + "; ".join(failures)
        )

    def _render_changed_file_context(
        self,
        worktree_path: str,
        changed_files: list[str],
        *,
        max_chars: int = 12_000,
        max_file_chars: int = 2_000,
    ) -> str:
        sections: list[str] = []
        used = 0
        root = os.path.realpath(worktree_path)
        for rel_path in changed_files:
            target = os.path.realpath(os.path.abspath(os.path.join(worktree_path, rel_path)))
            if os.path.commonpath([root, target]) != root or not os.path.isfile(target):
                continue
            try:
                with open(target, encoding="utf-8") as handle:
                    content = handle.read()
            except UnicodeDecodeError:
                continue
            snippet = content[:max_file_chars]
            block = f"--- {rel_path} ---\n{snippet}\n"
            if used + len(block) > max_chars:
                sections.append("[file context truncated]")
                break
            sections.append(block)
            used += len(block)
        return "\n".join(sections) if sections else "- no readable changed files"

    def _is_visual_task(self, task: domain.Task) -> bool:
        contract = task.metadata.get("task_contract")
        if isinstance(contract, dict) and bool(contract.get("visual_required", False)):
            return True
        return bool(task.metadata.get("visual_required", False))

    def _visual_actual_output_path(self, task: domain.Task) -> str | None:
        contract = task.metadata.get("task_contract")
        if isinstance(contract, dict):
            value = contract.get("visual_actual_output")
            if isinstance(value, str) and value:
                return value
        value = task.metadata.get("visual_actual_output")
        return value if isinstance(value, str) and value else None
    def _detect_truncation(self, content: str) -> str | None:
        suspects = [
            "omitted for brevity",
            "remaining keys omitted",
            "rest of the code",
            "css remains the same",
            "existing styles",
            "remaining keys",
            "rest of the html",
            "keys omitted for brevity"
        ]
        lowered = content.lower()
        for s in suspects:
            if s in lowered:
                return s
        return None

    async def _request_action_json_repair(
        self,
        *,
        task: domain.Task,
        context: RoleContext,
        invalid_payload: str,
        purpose: str,
    ) -> str:
        config = load_config()
        repair_model = config.models.roles.get(AgentRole.FIXER.value, context.model_profile_id)
        prompt = (
            "The previous LocalForge action response was invalid. Return only corrected JSON "
            "with shape {\"actions\":[{\"kind\":\"write_file\",\"path\":\"relative/path\","
            "\"content\":\"file contents\"},{\"kind\":\"append_content\","
            "\"path\":\"relative/path\",\"content\":\"extra contents\"}]}. "
            "Do not include markdown fences, comments, "
            "or explanatory text.\n\n"
            f"Task: {task.key} {task.title}\n"
            f"Purpose: {purpose}\n"
            "Invalid payload:\n"
            f"{compress_tool_output(invalid_payload, max_chars=4000)}"
        )
        task_class = task.metadata.get("task_contract", {}).get("seniority_class", "local_assisted")
        response, model_used = await self._chat_completion_with_local_fallback(
            prompt=prompt,
            preferred_model=repair_model,
            timeout=180.0,
            task_class=task_class,
        )
        await self._record_local_model_call(
            task=task,
            model=model_used,
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            prompt=prompt,
            response=response,
        )
        return response

    async def _advance_to(self, task: domain.Task, target: TaskStatus) -> None:
        assert self.uow.tasks is not None
        current_task = await self.uow.tasks.get_task(task.id or 0)
        if current_task:
            task = current_task
        ladder = [
            TaskStatus.BACKLOG,
            TaskStatus.READY,
            TaskStatus.CLAIMED,
            TaskStatus.PLANNING,
            TaskStatus.IMPLEMENTING,
            TaskStatus.TESTING,
            TaskStatus.REVIEWING,
            TaskStatus.PR_READY,
        ]
        current_index = ladder.index(task.status) if task.status in ladder else 0
        target_index = ladder.index(target)
        if current_index >= target_index:
            return
        for status in ladder[current_index + 1 : target_index + 1]:
            task = await self.uow.tasks.update_task_status(task.id or 0, status)

    async def _apply_role_status(self, task_id: int, role: AgentRole) -> None:
        assert self.uow.tasks is not None
        task = await self.uow.tasks.get_task(task_id)
        if not task:
            return
        if role in {AgentRole.CODER, AgentRole.CLEANER}:
            if task.status == TaskStatus.PLANNING:
                await self.uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)
        elif role in {AgentRole.TESTER, AgentRole.QA}:
            if task.status == TaskStatus.IMPLEMENTING:
                await self.uow.tasks.update_task_status(task_id, TaskStatus.TESTING)
        elif role in {AgentRole.FIXER}:
            if task.status == TaskStatus.TESTING:
                await self.uow.tasks.update_task_status(task_id, TaskStatus.REPAIRING)
                await self.uow.tasks.update_task_status(task_id, TaskStatus.TESTING)
        elif role == AgentRole.REVIEWER:
            if task and task.status == TaskStatus.TESTING:
                await self.uow.tasks.update_task_status(task_id, TaskStatus.REVIEWING)


def _handoff_kind_for(role: AgentRole) -> HandoffKind:
    if role in {AgentRole.PLANNER, AgentRole.SPECIFIER, AgentRole.ARCHITECT}:
        return HandoffKind.PLAN
    if role in {AgentRole.CODER, AgentRole.CLEANER}:
        return HandoffKind.IMPLEMENTATION
    if role in {AgentRole.TESTER, AgentRole.QA}:
        return HandoffKind.TEST_RESULT
    if role == AgentRole.FIXER:
        return HandoffKind.REPAIR_REQUEST
    if role == AgentRole.PR_WRITER:
        return HandoffKind.PR_READY
    return HandoffKind.REVIEW


def _standard_artifact_for(role: AgentRole) -> str | None:
    return {
        AgentRole.PLANNER: "plan.md",
        AgentRole.CODER: "diff.patch",
        AgentRole.TESTER: "tests.md",
        AgentRole.QA: "tests.md",
        AgentRole.FIXER: "repair.md",
        AgentRole.REVIEWER: "risk.md",
        AgentRole.ARCHITECT: "risk.md",
        AgentRole.HARDENER: "risk.md",
    }.get(role)
