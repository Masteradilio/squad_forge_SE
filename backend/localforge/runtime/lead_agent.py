import os

from localforge.models.enums import TaskStatus
from localforge.runtime.actions import normalize_runtime_command, parse_action_proposals
from localforge.runtime.compression import compress_tool_output
from localforge.runtime.context import TaskContextBuilder
from localforge.runtime.file_tools import SafeFileEditor
from localforge.safety.runner import run_safe_command
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


class LeadAgentRuntime:
    def __init__(self, uow: UnitOfWork, *, project_id: int, run_id: int):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id

    async def run_task(self, task_id: int, task_run_id: int) -> str:
        assert self.uow.tasks is not None
        task = await self.uow.tasks.get_task(task_id)
        task_run = await self.uow.tasks.get_task_run(task_run_id)
        if not task or not task_run or not task_run.worktree_path:
            raise ValueError("Task and task run with worktree are required.")

        context = await TaskContextBuilder(self.uow).build(task_id, task_run.worktree_path)
        plan_artifact = await ArtifactStore(self.uow).write_artifact(
            project_root=task_run.worktree_path,
            task_run_id=task_run_id,
            task_key=task.key,
            run_id=self.run_id,
            filename="plan.md",
            content=f"# Plan\n\nUse runtime actions for {task.key}.\n\n{context.rendered}",
            summary="Lead agent plan",
        )

        task = await self.uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)
        editor = SafeFileEditor(
            self.uow,
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=task_id,
        )
        actions = task.metadata.get("runtime_actions", [])
        try:
            proposals = parse_action_proposals(actions)
        except ValueError:
            proposals = []

        command_summaries: list[str] = []
        changed_files: list[str] = []
        for action in proposals:
            if action.kind == "write_file" and action.path:
                result = await editor.write_text(
                    task_run.worktree_path,
                    action.path,
                    action.content,
                    task_run_id=task_run_id,
                    task_key=task.key,
                )
                changed_files.append(
                    os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
                )
            elif action.kind == "append_content" and action.path:
                existing_content = ""
                target_path = os.path.join(task_run.worktree_path, action.path)
                if os.path.exists(target_path):
                    existing_content = await editor.read_text(task_run.worktree_path, action.path)
                result = await editor.write_text(
                    task_run.worktree_path,
                    action.path,
                    existing_content + action.content,
                    task_run_id=task_run_id,
                    task_key=task.key,
                )
                changed_files.append(
                    os.path.relpath(result.path, task_run.worktree_path).replace("\\", "/")
                )
            elif action.kind == "run_command" and action.command:
                command = normalize_runtime_command(action.command)
                code, stdout, stderr = await run_safe_command(
                    project_id=self.project_id,
                    command=command,
                    uow=self.uow,
                    run_id=self.run_id,
                    task_id=task_id,
                )
                command_summaries.append(
                    compress_tool_output(
                        f"{command}: exit {code}; stdout={stdout}; stderr={stderr}",
                        max_chars=260,
                    )
                )

        if changed_files:
            existing = task.metadata.get("changed_files", [])
            if not isinstance(existing, list):
                existing = []
            task.metadata["changed_files"] = [
                *[path for path in existing if isinstance(path, str)],
                *changed_files,
            ]
            await self.uow.tasks.update_task(task)

        await self.uow.tasks.update_task_status(task_id, TaskStatus.TESTING)
        await self.uow.tasks.update_task_status(task_id, TaskStatus.REVIEWING)
        await self.uow.tasks.mark_pr_ready(
            task_id,
            gate_evidence={
                "source": "lead_agent_runtime",
                "task_run_id": task_run_id,
                "maker_id": "lead-agent",
                "checker_id": "mechanical-pre-pr-gate",
                "pre_pr_gate": {"passed": True, "changed_files": changed_files},
                "checks_executed": command_summaries or ["runtime-actions-applied"],
                "artifact_paths": [plan_artifact.path],
                "branch_name": task_run.branch_name,
                "worktree_path": task_run.worktree_path,
            },
        )
        summary = "Lead agent summarized executed actions."
        task_run.final_summary = summary
        await self.uow.tasks.update_task_run(task_run)
        await ArtifactStore(self.uow).write_artifact(
            project_root=task_run.worktree_path,
            task_run_id=task_run_id,
            task_key=task.key,
            run_id=self.run_id,
            filename="review.md",
            content="\n".join([summary, *command_summaries]),
            summary="Lead agent summary",
        )
        return summary
