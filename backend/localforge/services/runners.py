from abc import ABC, abstractmethod
from dataclasses import dataclass

from localforge.gitops.manager import WorktreeManager
from localforge.models import domain
from localforge.models.enums import RunMode


@dataclass(frozen=True)
class RunnerContext:
    worktree_path: str | None = None
    branch_name: str | None = None
    source_commit: str | None = None
    sandbox_id: str | None = None


class BaseTaskRunner(ABC):
    @abstractmethod
    async def setup(self, task: domain.Task, *, run_id: int, uow) -> RunnerContext:
        pass

    @abstractmethod
    async def execute(self, task_run: domain.TaskRun, *, uow) -> None:
        pass

    @abstractmethod
    async def checkpoint(self, task_run: domain.TaskRun, name: str, *, uow) -> str:
        pass

    @abstractmethod
    async def cleanup(self, task_run: domain.TaskRun, *, uow) -> None:
        pass


class LocalWorktreeTaskRunner(BaseTaskRunner):
    def __init__(self, project_id: int, run_mode: RunMode = RunMode.INTERACTIVE):
        self.project_id = project_id
        self.run_mode = run_mode

    async def setup(self, task: domain.Task, *, run_id: int, uow) -> RunnerContext:
        if task.id is None:
            raise ValueError("Cannot prepare a runner for a task without an ID.")
        manager = WorktreeManager(
            project_id=self.project_id,
            uow=uow,
            run_id=run_id,
            run_mode=self.run_mode,
        )
        worktree_path, branch_name, source_commit = await manager.setup_worktree_attempt(task.id)
        return RunnerContext(
            worktree_path=worktree_path,
            branch_name=branch_name,
            source_commit=source_commit,
            sandbox_id="local-worktree",
        )

    async def execute(self, task_run: domain.TaskRun, *, uow) -> None:
        return None

    async def checkpoint(self, task_run: domain.TaskRun, name: str, *, uow) -> str:
        manager = WorktreeManager(project_id=self.project_id, uow=uow)
        return await manager.create_checkpoint(task_run.task_id, name)

    async def cleanup(self, task_run: domain.TaskRun, *, uow) -> None:
        manager = WorktreeManager(project_id=self.project_id, uow=uow)
        await manager.cleanup_worktree(task_run.task_id)


class TaskRunnerPool:
    def __init__(self, runners: list[BaseTaskRunner]):
        if not runners:
            raise ValueError("TaskRunnerPool requires at least one runner.")
        self.runners = runners
        self._next_index = 0

    def acquire(self, task: domain.Task) -> BaseTaskRunner:
        runner = self.runners[self._next_index % len(self.runners)]
        self._next_index += 1
        return runner
