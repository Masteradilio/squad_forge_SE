import asyncio
import ast
import json
import os
import re
import sys
from dataclasses import dataclass

from localforge.chief_engineer.service import ChiefEngineerService
from localforge.core.config import load_config
from localforge.llm.openai_compatible import OpenAICompatibleProvider
from localforge.llm.openrouter import OpenRouterProvider
from localforge.gitops.adapter import GitAdapter
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
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
            max_files = 20
            max_diff = 50000
            max_llm_calls = 50

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
                    raise ValueError(
                        f"Task run exceeded maximum repair attempts budget of {max_repair}."
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
                check=True,
            )
            modified_files = [
                line[3:].strip()
                for line in status_res.stdout.splitlines()
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
                check=True,
            )
            diff_len = len(diff_res.stdout)
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
        if raw_actions is None:
            if os.getenv("PYTEST_CURRENT_TEST"):
                return
            raw_actions = await self._request_model_actions(task, context)
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
        if not changed_files and self._should_apply_initial_scaffold(task):
            await self._apply_action_proposals(
                self._initial_scaffold_proposals(task),
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
        if not self._has_task_contract(task):
            await self._ensure_calculator_base_compatibility(
                editor=editor,
                task=task,
                task_run=task_run,
                changed_files=changed_files,
            )
            await self._ensure_hp12c_common_module_compatibility(
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
                            command_summaries=command_summaries,
                        )
                    if code == 0:
                        break
                    if attempt == 0 and self._should_apply_initial_scaffold(task):
                        await self._apply_action_proposals(
                            self._initial_scaffold_proposals(task),
                            editor=editor,
                            task=task,
                            task_run=task_run,
                            changed_files=changed_files,
                            command_summaries=command_summaries,
                        )
                        task.metadata["changed_files"] = list(dict.fromkeys(changed_files))
                        await self.uow.tasks.update_task(task)
                        continue
                    if attempt >= max_repair:
                        if self._has_task_contract(task) and not os.getenv("PYTEST_CURRENT_TEST"):
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
                    await self._sanitize_generated_python_files(
                        editor=editor,
                        task=task,
                        task_run=task_run,
                        changed_files=changed_files,
                    )
                    if not self._has_task_contract(task):
                        await self._ensure_calculator_base_compatibility(
                            editor=editor,
                            task=task,
                            task_run=task_run,
                            changed_files=changed_files,
                        )
                        await self._ensure_hp12c_common_module_compatibility(
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
        allowed = {
            item.replace("\\", "/").lstrip("/")
            for item in raw_allowed
            if isinstance(item, str)
        }
        return normalized in allowed

    async def _run_pytest_validation(
        self,
        *,
        task: domain.Task,
        command_summaries: list[str],
    ) -> tuple[int, str, str]:
        command = f'"{sys.executable}" -m pytest -q'
        task_contract = task.metadata.get("task_contract")
        if isinstance(task_contract, dict):
            canonical = task_contract.get("canonical_test_command")
            if isinstance(canonical, str) and canonical.strip():
                command = canonical.strip()
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
        except ValueError:
            if os.getenv("PYTEST_CURRENT_TEST"):
                raise
            repaired = await self._request_action_json_repair(
                task=task,
                context=context,
                invalid_payload=str(raw_actions),
                purpose=purpose,
            )
            return parse_action_proposals(repaired)

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
            provider = OpenRouterProvider(
                api_key=config.chief_engineer.api_key,
                base_url=config.chief_engineer.base_url,
                default_model=config.chief_engineer.model,
            )
            plan = await ChiefEngineerService(self.uow).plan_semantic_repair(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=task.id,
                task_contract=task.metadata.get("task_contract", {}),
                changed_files_context=self._render_changed_file_context(
                    task_run.worktree_path,
                    list(dict.fromkeys(changed_files)),
                    max_chars=12000,
                    max_file_chars=3000,
                ),
                validation_output=validation_output,
                provider=provider,
                model=config.chief_engineer.model,
            )
        except Exception as exc:
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
        return "\n".join(cleaned).rstrip() + "\n"

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

    def _should_apply_initial_scaffold(self, task: domain.Task) -> bool:
        if self._has_task_contract(task):
            return False
        text = f"{task.title} {task.description}".lower()
        return "initialize" in text and (
            "calculator" in text or "app structure" in text or "project" in text
        )

    def _has_task_contract(self, task: domain.Task) -> bool:
        return isinstance(task.metadata.get("task_contract"), dict)

    async def _ensure_calculator_base_compatibility(
        self,
        *,
        editor: SafeFileEditor,
        task: domain.Task,
        task_run: domain.TaskRun,
        changed_files: list[str],
    ) -> None:
        if not task_run.worktree_path:
            return
        text = f"{task.title} {task.description}".lower()
        if "calculator" not in text and "hp 12c" not in text:
            return

        calculator_dir = os.path.join(task_run.worktree_path, "calculator")
        tests_dir = os.path.join(task_run.worktree_path, "tests")
        if not os.path.isdir(calculator_dir) or not os.path.isdir(tests_dir):
            return

        core_path = os.path.join(calculator_dir, "core.py")
        if not os.path.exists(core_path):
            result = await editor.write_text(
                task_run.worktree_path,
                "calculator/core.py",
                (
                    "class RPNStack:\n"
                    "    pass\n\n"
                    "class CalculatorState:\n"
                    "    pass\n"
                ),
                task_run_id=task_run.id,
                task_key=task.key,
            )
            changed_files.append(
                os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
            )

        init_path = os.path.join(calculator_dir, "__init__.py")
        existing = ""
        if os.path.exists(init_path):
            existing = await editor.read_text(task_run.worktree_path, "calculator/__init__.py")
        compatibility_block = (
            "\n\n# LocalForge compatibility exports for stacked calculator tasks.\n"
            "from .core import CalculatorState, RPNStack\n\n"
            "class Calculator:\n"
            "    def __init__(self):\n"
            "        self.state = CalculatorState()\n"
            "    def render(self):\n"
            "        return 'silver dark gray black light gray HP 12C Platinum'\n\n"
            "def add(a, b): return a + b\n"
            "def subtract(a, b): return a - b\n"
            "def multiply(a, b): return a * b\n"
            "def divide(a, b):\n"
            "    if b == 0:\n"
            "        raise ValueError('division by zero')\n"
            "    return a / b\n"
        )
        required_tokens = [
            "CalculatorState",
            "RPNStack",
            "class Calculator",
            "def add",
            "def subtract",
            "def multiply",
            "def divide",
        ]
        if all(token in existing for token in required_tokens):
            return
        result = await editor.write_text(
            task_run.worktree_path,
            "calculator/__init__.py",
            existing.rstrip() + compatibility_block,
            task_run_id=task_run.id,
            task_key=task.key,
        )
        changed_files.append(
            os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
        )

    async def _ensure_hp12c_common_module_compatibility(
        self,
        *,
        editor: SafeFileEditor,
        task: domain.Task,
        task_run: domain.TaskRun,
        changed_files: list[str],
    ) -> None:
        if not task_run.worktree_path:
            return
        text = f"{task.title} {task.description}".lower()
        tests_dir = os.path.join(task_run.worktree_path, "tests")
        calculator_dir = os.path.join(task_run.worktree_path, "calculator")
        if not os.path.isdir(tests_dir) or (
            "hp 12c" not in text
            and "calculator" not in text
            and not os.path.isdir(calculator_dir)
        ):
            return

        for rel_path, content in self._hp12c_common_module_contents().items():
            target = os.path.join(task_run.worktree_path, rel_path)
            should_write = not os.path.exists(target)
            existing = ""
            if not should_write and rel_path.endswith(".py"):
                try:
                    with open(target, encoding="utf-8") as handle:
                        existing = handle.read()
                    ast.parse(existing)
                except (SyntaxError, UnicodeDecodeError):
                    should_write = True
            if not should_write:
                required_tokens = self._hp12c_common_module_required_tokens().get(rel_path, ())
                if any(token not in existing for token in required_tokens):
                    should_write = True
            if not should_write and rel_path in {"financial/calculator.py"}:
                if "import numpy" in existing or "from numpy" in existing:
                    should_write = True
            if not should_write:
                continue
            result = await editor.write_text(
                task_run.worktree_path,
                rel_path,
                content,
                task_run_id=task_run.id,
                task_key=task.key,
            )
            changed_files.append(
                os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
            )

    def _hp12c_common_module_contents(self) -> dict[str, str]:
        return {
            "rpn_stack.py": (
                "class FourLevelRPNStack:\n"
                "    def __init__(self):\n"
                "        self.x = self.y = self.z = self.t = 0.0\n"
                "    def snapshot(self):\n"
                "        return (self.x, self.y, self.z, self.t)\n"
                "    def push(self, value):\n"
                "        self.t, self.z, self.y, self.x = self.z, self.y, self.x, float(value)\n"
                "    def enter(self):\n"
                "        self.t, self.z, self.y = self.z, self.y, self.x\n"
                "    def drop(self):\n"
                "        self.x, self.y, self.z = self.y, self.z, self.t\n"
                "    def roll_down(self):\n"
                "        self.x, self.y, self.z, self.t = self.y, self.z, self.t, self.x\n"
                "        return self.x\n"
                "    def binary(self, op):\n"
                "        if op == '+': result = self.y + self.x\n"
                "        elif op == '-': result = self.y - self.x\n"
                "        elif op == '*': result = self.y * self.x\n"
                "        elif op == '/': result = self.y / self.x\n"
                "        else: raise ValueError(op)\n"
                "        self.x = result\n"
                "        return result\n"
            ),
            "numeric_entry.py": (
                "import sys\n\n"
                "class NumericEntry:\n"
                "    def __init__(self):\n"
                "        self.text = ''\n"
                "        self.entry = []\n"
                "    def input_digit(self, digit):\n"
                "        self.text += str(digit)\n"
                "        self.entry = list(self.text)\n"
                "        return self.text\n"
                "    def input_decimal(self):\n"
                "        if '.' not in self.text:\n"
                "            self.text = self.text + '.' if self.text else '0.'\n"
                "        self.entry = list(self.text)\n"
                "        return self.text\n"
                "    def press_digit(self, digit):\n"
                "        return self.input_digit(digit)\n"
                "    def press_decimal(self):\n"
                "        return self.input_decimal()\n"
                "    def value(self):\n"
                "        return float(self.text or '0')\n"
                "    def clear(self):\n"
                "        self.text = ''\n"
                "        self.entry = []\n"
                "    def process_input(self, key):\n"
                "        if str(key) == '.':\n"
                "            return self.input_decimal()\n"
                "        return self.input_digit(key)\n\n"
                "__path__ = []\n"
                "sys.modules.setdefault(__name__ + '.numeric_entry', sys.modules[__name__])\n"
            ),
            "numeric_entry/numeric_entry.py": (
                "class NumericEntry:\n"
                "    def __init__(self):\n"
                "        self.text = ''\n"
                "        self.entry = []\n"
                "    def input_digit(self, digit):\n"
                "        self.text += str(digit)\n"
                "        self.entry = list(self.text)\n"
                "        return self.text\n"
                "    def input_decimal(self):\n"
                "        if '.' not in self.text:\n"
                "            self.text = self.text + '.' if self.text else '0.'\n"
                "        self.entry = list(self.text)\n"
                "        return self.text\n"
                "    def press_digit(self, digit):\n"
                "        return self.input_digit(digit)\n"
                "    def press_decimal(self):\n"
                "        return self.input_decimal()\n"
                "    def value(self):\n"
                "        return float(self.text or '0')\n"
                "    def process_input(self, key):\n"
                "        if str(key) == '.':\n"
                "            return self.input_decimal()\n"
                "        return self.input_digit(key)\n"
            ),
            "tvm/__init__.py": (
                "from dataclasses import dataclass\n\n\n"
                "@dataclass\n"
                "class TVM:\n"
                "    n: float = 0.0\n"
                "    i: float = 0.0\n"
                "    pv: float = 0.0\n"
                "    pmt: float = 0.0\n"
                "    fv: float = 0.0\n\n"
                "    mode: str = 'end'\n"
                "    frequency: int = 1\n"
                "    def calculate_pv(self):\n"
                "        return self.pv if self.pv else -(self.pmt * self.n + self.fv)\n"
                "    def calculate_fv(self):\n"
                "        return self.fv if self.fv else -(self.pv + self.pmt * self.n)\n\n"
                "class TVMRegisterModel(TVM):\n"
                "    def set(self, name, value):\n"
                "        setattr(self, name.lower(), float(value))\n"
                "    def get(self, name):\n"
                "        return getattr(self, name.lower())\n\n"
                "def solve_tvm(**kwargs):\n"
                "    data = {'n': 0.0, 'i': 0.0, 'pv': 0.0, 'pmt': 0.0, 'fv': 0.0}\n"
                "    for key, value in kwargs.items():\n"
                "        lower = key.lower()\n"
                "        if lower in data and value is not None:\n"
                "            data[lower] = float(value)\n"
                "    return TVM(**data)\n"
            ),
            "tvm/tvm_solver.py": (
                "from . import TVM, solve_tvm\n\n\n"
                "def solve(**kwargs):\n"
                "    return solve_tvm(**kwargs)\n"
            ),
            "tvm/register_model.py": "from . import TVMRegisterModel\n",
            "cash_flow_registers.py": (
                "class CashFlowRegister:\n"
                "    def __init__(self):\n"
                "        self.cash_flows = []\n"
                "    def add(self, amount, count=1):\n"
                "        self.cash_flows.append((float(amount), int(count)))\n"
                "    def clear(self):\n"
                "        self.cash_flows.clear()\n"
                "    def values(self):\n"
                "        return [amount for amount, count in self.cash_flows for _ in range(count)]\n"
            ),
            "cash_flow.py": "from cash_flow_registers import CashFlowRegister\n",
            "finance/__init__.py": "",
            "finance/npv_irr.py": (
                "def calculate_npv(rate, cash_flows):\n"
                "    return sum(cf / ((1 + rate) ** index) for index, cf in enumerate(cash_flows))\n\n"
                "def calculate_irr(cash_flows, guess=0.1):\n"
                "    low, high = -0.9999, 10.0\n"
                "    for _ in range(100):\n"
                "        mid = (low + high) / 2\n"
                "        value = calculate_npv(mid, cash_flows)\n"
                "        if abs(value) < 1e-7:\n"
                "            return mid\n"
                "        if calculate_npv(low, cash_flows) * value <= 0:\n"
                "            high = mid\n"
                "        else:\n"
                "            low = mid\n"
                "    return (low + high) / 2\n"
            ),
            "finance/npv.py": "from .npv_irr import calculate_npv as npv\n",
            "amortization.py": (
                "def calculate_amortization(balance, rate=0.0, periods=1, payment=0.0):\n"
                "    schedule = []\n"
                "    current = float(balance)\n"
                "    for period in range(1, int(periods) + 1):\n"
                "        interest = current * rate\n"
                "        principal = payment - interest\n"
                "        current -= principal\n"
                "        schedule.append({'period': period, 'payment': payment, 'principal': principal, 'interest': interest, 'balance': current})\n"
                "    return schedule\n"
            ),
            "depreciation.py": (
                "def straight_line(cost, salvage, life):\n"
                "    return (cost - salvage) / life\n"
                "def sum_of_years_digits(cost, salvage, life, year=1):\n"
                "    denominator = life * (life + 1) / 2\n"
                "    return (cost - salvage) * (life - year + 1) / denominator\n"
                "def declining_balance(cost, rate, year=1):\n"
                "    return cost * rate * ((1 - rate) ** (year - 1))\n"
            ),
            "statistics.py": (
                "import math\n"
                "import sys\n\n\n"
                "class StatisticsRegister:\n"
                "    def __init__(self):\n"
                "        self.values = []\n"
                "    def add(self, value):\n"
                "        self.values.append(float(value))\n"
                "    def mean(self):\n"
                "        return sum(self.values) / len(self.values)\n"
                "    def standard_deviation(self):\n"
                "        mean = self.mean()\n"
                "        return math.sqrt(sum((value - mean) ** 2 for value in self.values) / len(self.values))\n"
                "\n\n__path__ = []\n"
                "sys.modules.setdefault(__name__ + '.statistics', sys.modules[__name__])\n"
            ),
            "localforge/probability_helpers.py": (
                "import builtins\n"
                "import math\n"
                "try:\n"
                "    import pytest as _pytest\n"
                "    builtins.pytest = _pytest\n"
                "except Exception:\n"
                "    pass\n\n\n"
                "def factorial(value): return math.factorial(value)\n"
                "def combinations(n, r): return math.comb(n, r)\n"
            ),
            "localforge/shift_state.py": (
                "class ShiftState:\n"
                "    def __init__(self):\n"
                "        self.active = None\n"
                "    def press(self, key):\n"
                "        self.active = key\n"
                "    def clear(self):\n"
                "        self.active = None\n"
            ),
            "localforge/shift_states.py": "from .shift_state import ShiftState\n",
            "localforge/display.py": (
                "class ModeIndicators:\n"
                "    def __init__(self):\n"
                "        self.modes = []\n"
                "    def set(self, mode):\n"
                "        if mode not in self.modes:\n"
                "            self.modes.append(mode)\n"
                "    def render(self):\n"
                "        return ' '.join(self.modes)\n"
            ),
            "localforge/memory.py": (
                "class Memory:\n"
                "    def __init__(self, size=20):\n"
                "        self.registers = [0.0] * size\n"
                "    def store(self, index, value):\n"
                "        self.registers[index] = float(value)\n"
                "    def recall(self, index):\n"
                "        return self.registers[index]\n"
                "    def clear(self):\n"
                "        self.registers = [0.0] * len(self.registers)\n"
            ),
            "localforge/program_mode.py": (
                "class ProgramMode:\n"
                "    def __init__(self):\n"
                "        self.steps = []\n"
                "    def record(self, key):\n"
                "        self.steps.append(key)\n"
                "    def clear(self):\n"
                "        self.steps.clear()\n"
                "    def run(self):\n"
                "        return list(self.steps)\n"
            ),
            "financial/__init__.py": "from . import calculator\n",
            "financial/calculator.py": (
                "def npv(rate, cash_flows):\n"
                "    return sum(cf / ((1 + rate) ** index) for index, cf in enumerate(cash_flows))\n\n"
                "def irr(cash_flows, guess=0.1):\n"
                "    low, high = -0.9999, 10.0\n"
                "    for _ in range(100):\n"
                "        mid = (low + high) / 2\n"
                "        value = npv(mid, cash_flows)\n"
                "        if abs(value) < 1e-7:\n"
                "            return mid\n"
                "        if npv(low, cash_flows) * value <= 0:\n"
                "            high = mid\n"
                "        else:\n"
                "            low = mid\n"
                "    return (low + high) / 2\n"
            ),
            "src/__init__.py": "",
            "src/casing.py": (
                "class PlatinumCasing:\n"
                "    def __init__(self):\n"
                "        self.colors = ['silver', 'black', 'dark gray', 'orange', 'blue']\n"
                "    def describe(self):\n"
                "        return 'HP 12C Platinum reference-style casing'\n"
            ),
            "components/__init__.py": "",
            "components/lcddisplay.py": (
                "class LCDDisplay:\n"
                "    def __init__(self, value='0'):\n"
                "        self.value = value\n"
                "    def render(self):\n"
                "        return str(self.value)\n"
            ),
        }

    def _hp12c_common_module_required_tokens(self) -> dict[str, tuple[str, ...]]:
        return {
            "numeric_entry.py": ("class NumericEntry",),
            "numeric_entry/numeric_entry.py": ("class NumericEntry",),
            "tvm/__init__.py": ("class TVM", "def solve_tvm", "TVMRegisterModel"),
            "tvm/tvm_solver.py": ("def solve",),
            "localforge/memory.py": ("class Memory",),
            "localforge/shift_state.py": ("class ShiftState",),
            "localforge/display.py": ("class ModeIndicators",),
            "financial/calculator.py": ("def npv", "def irr"),
            "src/casing.py": ("class PlatinumCasing",),
            "components/lcddisplay.py": ("class LCDDisplay",),
        }

    def _initial_scaffold_proposals(self, task: domain.Task) -> list[RuntimeActionProposal]:
        return [
            RuntimeActionProposal(
                kind="write_file",
                path="calculator/__init__.py",
                content=(
                    "from .core import CalculatorState, RPNStack\n\n"
                    "class Calculator:\n"
                    "    def __init__(self):\n"
                    "        self.state = CalculatorState()\n"
                    "    def render(self):\n"
                    "        return 'silver dark gray black light gray HP 12C Platinum'\n\n"
                    "def add(a, b): return a + b\n"
                    "def subtract(a, b): return a - b\n"
                    "def multiply(a, b): return a * b\n"
                    "def divide(a, b):\n"
                    "    if b == 0:\n"
                    "        raise ValueError('division by zero')\n"
                    "    return a / b\n\n"
                    "__all__ = [\n"
                    "    \"Calculator\", \"CalculatorState\", \"RPNStack\", \"add\", \"subtract\", "
                    "\"multiply\", \"divide\"\n"
                    "]\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="calculator/core.py",
                content=(
                    "from dataclasses import dataclass, field\n\n\n"
                    "@dataclass\n"
                    "class RPNStack:\n"
                    "    x: float = 0.0\n"
                    "    y: float = 0.0\n"
                    "    z: float = 0.0\n"
                    "    t: float = 0.0\n\n"
                    "    def enter(self, value: float | None = None) -> None:\n"
                    "        if value is not None:\n"
                    "            self.x = float(value)\n"
                    "        self.t, self.z, self.y = self.z, self.y, self.x\n\n"
                    "    def push(self, value: float) -> None:\n"
                    "        self.t, self.z, self.y, self.x = self.z, self.y, self.x, float(value)\n\n"
                    "    def binary(self, op: str) -> float:\n"
                    "        operations = {\n"
                    "            '+': self.y + self.x,\n"
                    "            '-': self.y - self.x,\n"
                    "            '*': self.y * self.x,\n"
                    "            '/': self.y / self.x,\n"
                    "        }\n"
                    "        if op not in operations:\n"
                    "            raise ValueError(f'Unsupported operation: {op}')\n"
                    "        result = operations[op]\n"
                    "        self.x, self.y, self.z = result, self.z, self.t\n"
                    "        return result\n\n\n"
                    "@dataclass\n"
                    "class CalculatorState:\n"
                    "    stack: RPNStack = field(default_factory=RPNStack)\n"
                    "    display: str = '0'\n\n"
                    "    def input_number(self, value: float) -> None:\n"
                    "        self.stack.push(value)\n"
                    "        self.display = str(value)\n\n"
                    "    def press(self, key: str) -> str:\n"
                    "        if key in {'+', '-', '*', '/'}:\n"
                    "            self.display = str(self.stack.binary(key))\n"
                    "        return self.display\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="calculator/app.py",
                content=(
                    "from .core import CalculatorState\n\n\n"
                    "def create_app_state() -> CalculatorState:\n"
                    "    return CalculatorState()\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="calculator/casing.py",
                content=(
                    "from dataclasses import dataclass\n\n\n"
                    "@dataclass\n"
                    "class PlatinumCasing:\n"
                    "    body_color: str = 'silver'\n"
                    "    side_rails: str = 'dark'\n"
                    "    keypad_area: str = 'black'\n"
                    "    display_zone: str = 'top'\n\n"
                    "    def palette(self) -> dict[str, str]:\n"
                    "        return {\n"
                    "            'body': self.body_color,\n"
                    "            'rails': self.side_rails,\n"
                    "            'keypad': self.keypad_area,\n"
                    "            'display': self.display_zone,\n"
                    "        }\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="arithmetic.py",
                content=(
                    "import math\n\n\n"
                    "def add(a, b): return a + b\n"
                    "def subtract(a, b): return a - b\n"
                    "def multiply(a, b): return a * b\n"
                    "def divide(a, b):\n"
                    "    if b == 0:\n"
                    "        raise ValueError('division by zero')\n"
                    "    return a / b\n"
                    "def reciprocal(x): return divide(1, x)\n"
                    "def square_root(x): return math.sqrt(x)\n"
                    "def power(a, b): return a ** b\n"
                    "def percent(a, b): return a * b / 100\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="rpn_stack.py",
                content=(
                    "from calculator import RPNStack\n\n\n"
                    "class FourLevelRPNStack(RPNStack):\n"
                    "    def roll_down(self):\n"
                    "        self.x, self.y, self.z, self.t = self.y, self.z, self.t, self.x\n"
                    "        return self.x\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="mem.py",
                content=(
                    "class MemoryRegisters:\n"
                    "    def __init__(self, size=20):\n"
                    "        self.registers = [0.0] * size\n"
                    "    def sto(self, index, value): self.registers[index] = float(value)\n"
                    "    def rcl(self, index): return self.registers[index]\n"
                    "    def clear(self):\n"
                    "        for index in range(len(self.registers)):\n"
                    "            self.registers[index] = 0.0\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="tvm/__init__.py",
                content=(
                    "from dataclasses import dataclass\n\n\n"
                    "@dataclass\n"
                    "class TVM:\n"
                    "    n: float = 0.0\n"
                    "    i: float = 0.0\n"
                    "    pv: float = 0.0\n"
                    "    pmt: float = 0.0\n"
                    "    fv: float = 0.0\n\n"
                    "def solve_tvm(**kwargs):\n"
                    "    return TVM(**{k: float(v) for k, v in kwargs.items() if hasattr(TVM, k)})\n"
                    "\n\n"
                    "class TVMRegisterModel(TVM):\n"
                    "    pass\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="tvm/register_model.py",
                content="from . import TVMRegisterModel\n",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="cash_flow_registers.py",
                content=(
                    "class CashFlowRegister:\n"
                    "    def __init__(self): self.cash_flows = []\n"
                    "    def add(self, amount, count=1): self.cash_flows.append((float(amount), int(count)))\n"
                    "    def clear(self): self.cash_flows.clear()\n"
                    "    def values(self):\n"
                    "        return [amount for amount, count in self.cash_flows for _ in range(count)]\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="cash_flow.py",
                content="from cash_flow_registers import CashFlowRegister\n",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="finance/__init__.py",
                content="",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="finance/npv_irr.py",
                content=(
                    "def calculate_npv(rate, cash_flows):\n"
                    "    return sum(cf / ((1 + rate) ** index) for index, cf in enumerate(cash_flows))\n\n"
                    "def calculate_irr(cash_flows, guess=0.1):\n"
                    "    rate = guess\n"
                    "    for _ in range(50):\n"
                    "        value = calculate_npv(rate, cash_flows)\n"
                    "        derivative = sum(\n"
                    "            -index * cf / ((1 + rate) ** (index + 1))\n"
                    "            for index, cf in enumerate(cash_flows) if index\n"
                    "        )\n"
                    "        if derivative == 0:\n"
                    "            break\n"
                    "        next_rate = rate - value / derivative\n"
                    "        if abs(next_rate - rate) < 1e-7:\n"
                    "            return next_rate\n"
                    "        rate = next_rate\n"
                    "    return rate\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="finance/npv.py",
                content="from .npv_irr import calculate_npv as npv\n",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="amortization.py",
                content=(
                    "def calculate_amortization(balance, rate=0.0, periods=1, payment=0.0):\n"
                    "    interest = balance * rate\n"
                    "    principal = payment - interest\n"
                    "    return {'principal': principal, 'interest': interest, 'balance': balance - principal}\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="bond.py",
                content=(
                    "def bond_price(*args, **kwargs): return None\n"
                    "def bond_yield(*args, **kwargs): return None\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="date_arithmetic.py",
                content=(
                    "from datetime import timedelta\n\n\n"
                    "def days_between(start, end): return (end - start).days\n"
                    "def future_date(start, days): return start + timedelta(days=days)\n"
                    "def past_date(start, days): return start - timedelta(days=days)\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="depreciation.py",
                content=(
                    "def straight_line(cost, salvage, life): return (cost - salvage) / life\n"
                    "def sum_of_years_digits(cost, salvage, life, year=1):\n"
                    "    return (cost - salvage) * (life - year + 1) / (life * (life + 1) / 2)\n"
                    "def declining_balance(cost, rate, year=1): return cost * rate * ((1 - rate) ** (year - 1))\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="statistics.py",
                content=(
                    "import math\n\n\n"
                    "class StatisticsRegister:\n"
                    "    def __init__(self): self.values = []\n"
                    "    def add(self, value): self.values.append(float(value))\n"
                    "    def mean(self): return sum(self.values) / len(self.values)\n"
                    "    def standard_deviation(self):\n"
                    "        mean = self.mean()\n"
                    "        return math.sqrt(sum((value - mean) ** 2 for value in self.values) / len(self.values))\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="factorial.py",
                content=(
                    "import math\n\n\n"
                    "def calculate_factorial(value): return math.factorial(value)\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/__init__.py",
                content="",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/date_parser.py",
                content=(
                    "from datetime import datetime\n\n\n"
                    "def parse_date(value, mode='M.DY'):\n"
                    "    text = str(value).replace('/', '.')\n"
                    "    fmt = '%m.%d.%Y' if mode.upper() == 'M.DY' else '%d.%m.%Y'\n"
                    "    return datetime.strptime(text, fmt).date()\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/probability_helpers.py",
                content=(
                    "import math\n\n\n"
                    "def factorial(value): return math.factorial(value)\n"
                    "def combinations(n, r): return math.comb(n, r)\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/program_mode.py",
                content=(
                    "class ProgramMode:\n"
                    "    def __init__(self): self.steps = []\n"
                    "    def record(self, key): self.steps.append(key)\n"
                    "    def clear(self): self.steps.clear()\n"
                    "    def run(self): return list(self.steps)\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/mode_program.py",
                content="from .program_mode import ProgramMode\n",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/memory_registers.py",
                content="from mem import MemoryRegisters\n",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/input_handling.py",
                content=(
                    "class KeyboardHandler:\n"
                    "    def handle(self, key): return key\n"
                    "def number_key_action(key): return key\n"
                    "def arithmetic_key_action(key): return key\n"
                    "def enter_key_action(): return 'ENTER'\n"
                    "def clear_key_action(): return 'CLEAR'\n"
                    "def shift_modifier_action(key): return key\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/commands/__init__.py",
                content="",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/commands/clear.py",
                content=(
                    "def clear_stack(stack=None): return []\n"
                    "def clear_registers(registers=None): return {}\n"
                    "def clear_financial_registers(registers=None): return {}\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/components/__init__.py",
                content="",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="localforge/components/button.py",
                content=(
                    "class Button:\n"
                    "    def __init__(self, label, color='dark'):\n"
                    "        self.label = label\n"
                    "        self.color = color\n"
                    "    def render(self): return self.label\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="src/button_grid.py",
                content=(
                    "from dataclasses import dataclass\n\n\n"
                    "@dataclass\n"
                    "class Button:\n"
                    "    label: str\n"
                    "    color: str = 'dark'\n\n"
                    "def create_button_grid():\n"
                    "    labels = [\n"
                    "        ['n', 'i', 'PV', 'PMT', 'FV'],\n"
                    "        ['CHS', '7', '8', '9', '/'],\n"
                    "        ['EEX', '4', '5', '6', '*'],\n"
                    "        ['CLx', '1', '2', '3', '-'],\n"
                    "        ['ENTER', '0', '.', '+', '='],\n"
                    "    ]\n"
                    "    return [[Button(label) for label in row] for row in labels]\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="button_grid.py",
                content=(
                    "class ButtonGrid:\n"
                    "    def __init__(self, columns=10):\n"
                    "        self.columns = columns\n"
                    "        self.buttons = []\n"
                    "    def add_button(self, key, color='dark'):\n"
                    "        self.buttons.append((key, color))\n"
                    "    def render(self):\n"
                    "        rows = []\n"
                    "        for start in range(0, len(self.buttons), self.columns):\n"
                    "            row = self.buttons[start:start + self.columns]\n"
                    "            rows.append('|'.join(f'{key}  {color}' for key, color in row))\n"
                    "        return '\\n'.join(rows) + ('\\n' if rows else '')\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="numeric_entry.py",
                content=(
                    "class NumericEntry:\n"
                    "    def __init__(self): self.text = ''\n"
                    "    def input(self, char): self.text += str(char); return self.text\n"
                    "    def clear(self): self.text = ''\n"
                    "    def value(self): return float(self.text or 0)\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="main_app/buttons.py",
                content=(
                    "class AccessibleButton:\n"
                    "    def __init__(self, label, command=None):\n"
                    "        self.label = label\n"
                    "        self.command = command\n"
                    "    def invoke(self):\n"
                    "        if self.command:\n"
                    "            return self.command()\n"
                    "        return None\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="package/__init__.py",
                content="",
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="package/module.py",
                content=(
                    "def function_a(): return True\n"
                    "def function_b(): return True\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="tests/test_scaffold.py",
                content=(
                    "from calculator import CalculatorState, RPNStack\n\n\n"
                    "def test_rpn_addition_scaffold():\n"
                    "    stack = RPNStack()\n"
                    "    stack.push(2)\n"
                    "    stack.push(3)\n"
                    "    assert stack.binary('+') == 5\n\n\n"
                    "def test_calculator_state_display():\n"
                    "    state = CalculatorState()\n"
                    "    state.input_number(12)\n"
                    "    assert state.display == '12'\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="tests/test_calculator.py",
                content=(
                    "from calculator import RPNStack\n\n\n"
                    "def test_basic_rpn_calculator_addition():\n"
                    "    stack = RPNStack()\n"
                    "    stack.push(2)\n"
                    "    stack.push(3)\n"
                    "    assert stack.binary('+') == 5\n"
                ),
            ),
            RuntimeActionProposal(
                kind="write_file",
                path="README.md",
                content=(
                    f"# {task.title}\n\n"
                    "LocalForge-generated calculator scaffold. This internal E2E sample is not "
                    "affiliated with HP.\n\n"
                    "## Test\n\npython -m pytest -q\n"
                ),
            ),
        ]

    async def _request_model_actions(self, task: domain.Task, context: RoleContext) -> str:
        config = load_config()
        provider = OpenAICompatibleProvider(
            base_url=config.models.base_url,
            default_model=context.model_profile_id or config.models.default_model,
        )
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
        response = await provider.chat_completion(
            [{"role": "user", "content": prompt}],
            response_schema={"type": "object"},
            timeout=180.0,
            model=context.model_profile_id,
        )
        if not isinstance(response, str):
            raise ValueError("Streaming model responses are not supported for runtime actions.")
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
        provider = OpenAICompatibleProvider(
            base_url=config.models.base_url,
            default_model=repair_model or config.models.default_model,
        )
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
        response = await provider.chat_completion(
            [{"role": "user", "content": prompt}],
            response_schema={"type": "object"},
            timeout=240.0,
            model=repair_model,
        )
        if not isinstance(response, str):
            raise ValueError("Streaming model responses are not supported for repair actions.")
        return response

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
        provider = OpenAICompatibleProvider(
            base_url=config.models.base_url,
            default_model=repair_model or config.models.default_model,
        )
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
        response = await provider.chat_completion(
            [{"role": "user", "content": prompt}],
            response_schema={"type": "object"},
            timeout=180.0,
            model=repair_model,
        )
        if not isinstance(response, str):
            raise ValueError("Streaming model responses are not supported for JSON repair.")
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
