from localforge.models.enums import TaskStatus
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
        await ArtifactStore(self.uow).write_artifact(
            project_root=task_run.worktree_path,
            task_run_id=task_run_id,
            task_key=task.key,
            run_id=self.run_id,
            filename="plan.md",
            content=f"# Plan\n\nUse runtime actions for {task.key}.\n\n{context.rendered}",
            summary="Lead agent plan",
        )

        await self.uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)
        editor = SafeFileEditor(
            self.uow,
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=task_id,
        )
        actions = task.metadata.get("runtime_actions", [])
        if not isinstance(actions, list):
            actions = []

        command_summaries: list[str] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("kind") == "write_file":
                path = action.get("path")
                content = action.get("content", "")
                if isinstance(path, str) and isinstance(content, str):
                    await editor.write_text(
                        task_run.worktree_path,
                        path,
                        content,
                        task_run_id=task_run_id,
                        task_key=task.key,
                    )
            elif action.get("kind") == "run_command":
                command = action.get("command")
                if isinstance(command, str):
                    code, stdout, stderr = await run_safe_command(
                        project_id=self.project_id,
                        command=command,
                        uow=self.uow,
                        run_id=self.run_id,
                        task_id=task_id,
                    )
                    command_summaries.append(
                        f"{command}: exit {code}; stdout={stdout[:120]}; stderr={stderr[:120]}"
                    )

        await self.uow.tasks.update_task_status(task_id, TaskStatus.TESTING)
        await self.uow.tasks.update_task_status(task_id, TaskStatus.REVIEWING)
        await self.uow.tasks.update_task_status(task_id, TaskStatus.PR_READY)
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
