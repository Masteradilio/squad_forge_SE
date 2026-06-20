import asyncio
import logging
from datetime import datetime
from typing import Any

from localforge.gitops.manager import WorktreeManager
from localforge.models import domain
from localforge.models.enums import RunStatus, TaskRunStatus, TaskStatus
from localforge.services.runners import LocalWorktreeTaskRunner, TaskRunnerPool
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger("localforge.scheduler")


class Scheduler:
    """Orchestrates tasks execution loop, runs lifecycle transitions,
    resource limits, and background cleanup operations.
    """

    def __init__(
        self,
        project_id: int,
        run_id: int,
        max_parallel_tasks: int = 2,
        loop_interval: float = 0.5,
        db_manager: Any | None = None,
        runner_pool: TaskRunnerPool | None = None,
    ):
        self.project_id = project_id
        self.run_id = run_id
        self.max_parallel_tasks = max_parallel_tasks
        self.loop_interval = loop_interval
        self.db_manager = db_manager
        self.runner_pool = runner_pool or TaskRunnerPool(
            [LocalWorktreeTaskRunner(project_id=project_id)]
        )
        self._running = False
        self._task: asyncio.Task | None = None
        self._trigger_event = asyncio.Event()
        self._loop_count = 0

    async def start(self) -> None:
        """Start the scheduler background loop task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"Scheduler started for run {self.run_id}")

    async def stop(self) -> None:
        """Gracefully stop the scheduler background task."""
        if not self._running:
            return
        self._running = False
        self.trigger()  # Wake up if sleeping
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(f"Scheduler stopped for run {self.run_id}")

    def trigger(self) -> None:
        """Signal the scheduler to wake up and process immediately."""
        self._trigger_event.set()

    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                self._trigger_event.clear()
                self._loop_count += 1

                # Periodically perform background cleanup (every 10 iterations)
                if self._loop_count % 10 == 0:
                    await self._cleanup_orphans()

                # Process scheduling iteration
                await self._process_iteration()

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            # Wait for event trigger or interval timeout
            await self._wait_for_trigger()

    async def _wait_for_trigger(self) -> bool:
        """Wait until an event wakes the scheduler or the watchdog interval expires."""
        try:
            await asyncio.wait_for(self._trigger_event.wait(), timeout=self.loop_interval)
            return True
        except TimeoutError:
            return False

    async def _cleanup_orphans(self) -> None:
        """Call WorktreeManager to clean up orphan directories."""
        async with UnitOfWork(self.db_manager) as uow:
            manager = WorktreeManager(project_id=self.project_id, uow=uow)
            cleaned = await manager.cleanup_orphan_worktrees()
            if cleaned:
                logger.info(f"Cleaned up {len(cleaned)} orphan worktrees in background")

    async def _process_iteration(self) -> None:
        async with UnitOfWork(self.db_manager) as uow:
            assert uow.executions is not None
            assert uow.tasks is not None

            # 1. Check Run lifecycle state
            run = await uow.executions.get_run(self.run_id)
            if not run:
                logger.error(f"Run {self.run_id} not found. Stopping scheduler.")
                self._running = False
                return

            if run.status in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.PAUSED,
            ):
                # If run ended or paused, do not schedule new tasks
                return

            if run.status == RunStatus.PENDING:
                run.status = RunStatus.RUNNING
                await uow.executions.update_run(run)

            # 2. Get executing TaskRuns counts to respect limits
            tasks = await uow.tasks.list_tasks_for_project(self.project_id)

            # Gather statuses
            executing_count = 0
            all_done = True
            has_failed = False

            for t in tasks:
                if t.status in (
                    TaskStatus.CLAIMED,
                    TaskStatus.PLANNING,
                    TaskStatus.IMPLEMENTING,
                    TaskStatus.TESTING,
                    TaskStatus.REPAIRING,
                    TaskStatus.REVIEWING,
                ):
                    executing_count += 1
                    all_done = False
                elif t.status in (TaskStatus.BACKLOG, TaskStatus.READY):
                    all_done = False
                elif t.status == TaskStatus.FAILED_SAFE:
                    has_failed = True

            # If all tasks are in DONE or CANCELLED, mark run as completed
            if all_done:
                run.status = (
                    RunStatus.COMPLETED
                    if not has_failed
                    else RunStatus.FAILED
                )
                run.ended_at = datetime.utcnow()
                run.summary = (
                    "All tasks executed successfully."
                    if not has_failed
                    else "Execution contains safe failures."
                )
                await uow.executions.update_run(run)
                self._running = False
                return

            # If executing count has hit the max parallel tasks, do not schedule new ones
            if executing_count >= self.max_parallel_tasks:
                return

            # 3. Try to claim and execute READY tasks
            ready_tasks = [t for t in tasks if t.status == TaskStatus.READY]
            for t in ready_tasks:
                if executing_count >= self.max_parallel_tasks:
                    break

                assert t.id is not None
                # Resolve dependencies
                runnable = await uow.tasks.is_task_runnable(t.id, tasks)
                if runnable:
                    # Claim the task
                    # Update status READY -> CLAIMED -> PLANNING (as per transition rules)
                    await uow.tasks.update_task_status(t.id, TaskStatus.CLAIMED)
                    await uow.tasks.update_task_status(t.id, TaskStatus.PLANNING)

                    # Create a new TaskRun record
                    task_run_data = domain.TaskRun(
                        run_id=self.run_id,
                        task_id=t.id,
                        status=TaskRunStatus.RUNNING,
                    )
                    task_run = await uow.tasks.create_task_run(task_run_data)

                    runner = self.runner_pool.acquire(t)
                    runner_context = await runner.setup(t, run_id=self.run_id, uow=uow)

                    # Update task run with runner details
                    task_run.worktree_path = runner_context.worktree_path
                    task_run.branch_name = runner_context.branch_name
                    task_run.sandbox_id = runner_context.sandbox_id
                    await uow.tasks.update_task_run(task_run)

                    executing_count += 1
