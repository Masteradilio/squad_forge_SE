import asyncio
import logging
import os
import re
import shutil

from localforge.gitops.adapter import GitAdapter
from localforge.models.enums import RunMode, TaskStatus
from localforge.storage import UnitOfWork

logger = logging.getLogger(__name__)


def get_task_branch_name(task_key: str, title: str) -> str:
    """Generate task-isolated branch name using localforge/<task-key>-<slug>."""
    # Normalize slug
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")

    if len(slug) > 30:
        slug = slug[:30].strip("-")

    return f"localforge/{task_key.lower()}-{slug}"


class WorktreeManager:
    """Manager orchestration worktree mappings, checkpoints, and cleanups."""

    _locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_worktree_lock(cls, path: str) -> asyncio.Lock:
        norm_path = os.path.realpath(os.path.abspath(path))
        if norm_path not in cls._locks:
            cls._locks[norm_path] = asyncio.Lock()
        return cls._locks[norm_path]

    def __init__(
        self,
        project_id: int,
        uow: UnitOfWork,
        run_id: int | None = None,
        run_mode: RunMode = RunMode.INTERACTIVE,
    ):
        self.project_id = project_id
        self.uow = uow
        self.run_id = run_id
        self.run_mode = run_mode

    async def setup_worktree(self, task_id: int) -> tuple[str, str]:
        """Create a deterministic Git worktree branch for a task.

        Returns (worktree_path, branch_name).
        """
        assert self.uow.projects is not None
        assert self.uow.tasks is not None

        # 1. Retrieve project and task
        project = await self.uow.projects.get_project(self.project_id)
        if not project:
            raise ValueError(f"Project with ID {self.project_id} not found.")

        task = await self.uow.tasks.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")

        # 2. Determine paths and branch names
        branch_name = get_task_branch_name(task.key, task.title)
        if self.run_id is not None:
            branch_name = f"{branch_name}-run-{self.run_id}"
        worktree_path = os.path.realpath(
            os.path.abspath(
                os.path.join(
                    project.root_path,
                    ".localforge",
                    "worktrees",
                    task.key.lower(),
                )
            )
        )

        # 3. Create worktree using GitAdapter on main repo root
        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            task_id=None,  # Run in main repo context
            run_mode=self.run_mode,
        )

        default_branch = await git.default_branch()
        base_branch = await self._base_branch_for_task(task_id, default_branch)
        lock = self._get_worktree_lock(worktree_path)
        async with lock:
            # Prune any stale worktree registrations BEFORE attempting to add.
            # Windows reliably leaves branches registered but missing on disk
            # between runs; without this `git worktree add` aborts with
            # "is a missing but already registered worktree".
            await self._git_prune_stale_worktrees(git)
            await self._remove_stale_worktree_path(
                git, worktree_path, project.root_path
            )
            try:
                await git.create_worktree(
                    path=worktree_path,
                    branch_name=branch_name,
                    base_branch=base_branch,
                )
            except Exception:
                await self._remove_stale_worktree_path(
                    git, worktree_path, project.root_path
                )
                raise
        return worktree_path, branch_name

    async def _git_prune_stale_worktrees(self, git: GitAdapter) -> None:
        """Best-effort ``git worktree prune`` so registered but orphan worktrees
        stop blocking subsequent ``git worktree add`` runs."""
        try:
            await git._execute_git(["worktree", "prune"], use_task_context=False)
        except Exception:
            logger = logging.getLogger(__name__)
            logger.debug("git worktree prune was a no-op or failed; continuing")

    async def _remove_stale_worktree_path(
        self, git: GitAdapter, worktree_path: str, project_root: str
    ) -> None:
        worktrees_root = os.path.realpath(
            os.path.abspath(os.path.join(project_root, ".localforge", "worktrees"))
        )
        target = os.path.realpath(os.path.abspath(worktree_path))
        if os.path.commonpath([worktrees_root, target]) != worktrees_root:
            raise ValueError(f"Refusing to clean worktree path outside {worktrees_root}: {target}")
        if not os.path.exists(target):
            return
        try:
            await git.remove_worktree(target)
        except Exception:
            pass
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)

    async def _base_branch_for_task(self, task_id: int, default_branch: str) -> str:
        assert self.uow.tasks is not None

        task = await self.uow.tasks.get_task(task_id)
        if not task or not task.dependency_task_ids:
            return default_branch

        for dependency_id in reversed(task.dependency_task_ids):
            dependency = await self.uow.tasks.get_task(dependency_id)
            if not dependency or dependency.status not in (TaskStatus.PR_READY, TaskStatus.DONE):
                continue
            for task_run in await self.uow.tasks.list_runs_for_task(dependency_id):
                if task_run.branch_name:
                    return task_run.branch_name

        return default_branch

    async def create_checkpoint(self, task_id: int, checkpoint_name: str) -> str:
        """Create a checkpoint commit in the task's worktree.

        Returns the commit hash.
        """
        assert self.uow.tasks is not None
        task_runs = await self.uow.tasks.list_runs_for_task(task_id)
        if not task_runs or not task_runs[0].worktree_path:
            raise ValueError(f"No active worktree path registered for task ID {task_id}.")

        worktree_path = task_runs[0].worktree_path
        assert worktree_path is not None

        # Instantiate GitAdapter bound to the task context (which overrides
        # project_root to worktree)
        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            task_id=task_id,
            run_mode=self.run_mode,
        )

        lock = self._get_worktree_lock(worktree_path)
        async with lock:
            await git.commit(f"checkpoint:{checkpoint_name}")
            return await git.current_commit_hash()

    async def rollback_checkpoint(self, task_id: int, checkpoint_hash: str) -> None:
        """Revert worktree state to a specific commit hash."""
        assert self.uow.tasks is not None
        task_runs = await self.uow.tasks.list_runs_for_task(task_id)
        if not task_runs or not task_runs[0].worktree_path:
            raise ValueError(f"No active worktree path registered for task ID {task_id}.")

        worktree_path = task_runs[0].worktree_path
        assert worktree_path is not None

        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            task_id=task_id,
            run_mode=self.run_mode,
        )

        lock = self._get_worktree_lock(worktree_path)
        async with lock:
            await git.reset_hard(checkpoint_hash)

    async def cleanup_worktree(self, task_id: int) -> None:
        """Remove a task's worktree if eligible (DONE, FAILED_SAFE, CANCELLED)."""
        assert self.uow.tasks is not None
        task = await self.uow.tasks.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")

        # Enforce cleanup eligibility criteria
        eligible_statuses = {
            TaskStatus.DONE,
            TaskStatus.FAILED_SAFE,
            TaskStatus.CANCELLED,
        }
        if task.status not in eligible_statuses:
            raise ValueError(
                f"Task {task.key} status is '{task.status}'. "
                f"Cleanup is only allowed for final states: {eligible_statuses}"
            )

        task_runs = await self.uow.tasks.list_runs_for_task(task_id)
        if not task_runs or not task_runs[0].worktree_path:
            return  # No worktree to clean up

        worktree_path = task_runs[0].worktree_path
        assert worktree_path is not None

        # Execute git worktree remove from the main repository context
        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            task_id=None,
            run_mode=self.run_mode,
        )

        lock = self._get_worktree_lock(worktree_path)
        async with lock:
            try:
                await git.remove_worktree(worktree_path)
            except Exception:
                pass

            # Cleanup left-over directories recursively
            if os.path.exists(worktree_path):
                try:
                    shutil.rmtree(worktree_path)
                except Exception:
                    pass

    async def cleanup_orphan_worktrees(self) -> list[str]:
        """Scan .localforge/worktrees/ directory and remove any worktrees
        associated with non-active tasks.
        """
        assert self.uow.projects is not None
        assert self.uow.tasks is not None

        project = await self.uow.projects.get_project(self.project_id)
        if not project:
            return []

        worktrees_dir = os.path.realpath(
            os.path.abspath(
                os.path.join(
                    project.root_path,
                    ".localforge",
                    "worktrees",
                )
            )
        )

        if not os.path.exists(worktrees_dir):
            return []

        cleaned_paths: list[str] = []

        try:
            entries = os.listdir(worktrees_dir)
        except Exception:
            return []

        tasks = await self.uow.tasks.list_tasks_for_project(self.project_id)
        # Identify active tasks keys
        active_keys = {
            t.key.lower()
            for t in tasks
            if t.status not in (
                TaskStatus.DONE,
                TaskStatus.FAILED_SAFE,
                TaskStatus.CANCELLED,
            )
        }

        git = GitAdapter(
            project_id=self.project_id,
            uow=self.uow,
            run_id=self.run_id,
            task_id=None,
            run_mode=self.run_mode,
        )

        for entry in entries:
            # If the entry directory key is not in active keys, it's orphan
            if entry.lower() not in active_keys:
                worktree_path = os.path.realpath(
                    os.path.abspath(
                        os.path.join(
                            worktrees_dir,
                            entry,
                        )
                    )
                )

                lock = self._get_worktree_lock(worktree_path)
                async with lock:
                    try:
                        await git.remove_worktree(worktree_path)
                    except Exception:
                        pass

                    if os.path.exists(worktree_path):
                        try:
                            shutil.rmtree(worktree_path)
                        except Exception:
                            pass

                    cleaned_paths.append(worktree_path)

        return cleaned_paths
