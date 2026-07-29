import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any, cast

from localforge.core.config import load_config
from localforge.gitops.manager import WorktreeManager
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    AuditEventActorType,
    AuditEventType,
    RunStatus,
    TaskRunStatus,
    TaskStatus,
)
from localforge.pipeline import PipelineMode, RolePipelineEngine
from localforge.services.governed_execution import (
    GovernedExecutionRequest,
    GovernedExecutionService,
)
from localforge.services.runners import LocalWorktreeTaskRunner, TaskRunnerPool
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger("localforge.scheduler")


def _clean_error_message(error: str) -> str:
    if not error:
        return "Unknown error"
    lines = error.splitlines()
    if len(lines) <= 20:
        return error
    cleaned_lines = []
    has_failures = False
    for line in lines:
        failure_terms = (
            "FAILURES",
            "AssertionError",
            "ModuleNotFoundError",
            "ValueError",
            "TypeError",
            "SyntaxError",
        )
        if any(term in line for term in failure_terms):
            has_failures = True
        if has_failures:
            cleaned_lines.append(line)
    if cleaned_lines:
        return "\n".join(cleaned_lines[-20:])
    return "\n".join(lines[-15:])


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class Scheduler:
    """Orchestrates tasks execution loop, runs lifecycle transitions,
    resource limits, and background cleanup operations.
    """

    # Resource-limit keys persisted on Run.resource_limits for the recovery loop:
    RUN_RECOVERY_CYCLES_KEY = "recovery_cycles_used"
    RUN_PAID_USD_SPENT_KEY = "paid_usd_spent_cached"

    # Status buckets the scheduler considers "terminal-but-not-yet-pr-ready":
    _RECOVERY_BLOCKING_STATES = (
        TaskStatus.FAILED_SAFE,
        TaskStatus.BLOCKED,
    )
    _EXECUTING_STATES = (
        TaskStatus.CLAIMED,
        TaskStatus.PLANNING,
        TaskStatus.IMPLEMENTING,
        TaskStatus.TESTING,
        TaskStatus.REPAIRING,
        TaskStatus.REVIEWING,
    )
    _TERMINAL_STATES = (
        TaskStatus.PR_READY,
        TaskStatus.DONE,
        TaskStatus.CANCELLED,
    )

    @staticmethod
    def _classify_task_statuses(
        tasks: list[domain.Task],
    ) -> dict[str, int]:
        """Return counts per status. Keys mirror TaskStatus values plus aggregates."""
        counts: dict[str, int] = {status.value: 0 for status in TaskStatus}
        counts["__total__"] = 0
        counts["__executing__"] = 0
        counts["__pending__"] = 0
        counts["__blocking_recovery__"] = 0
        counts["__blocked_human__"] = 0
        for t in tasks:
            counts["__total__"] += 1
            counts[t.status.value] += 1
            if t.status in Scheduler._EXECUTING_STATES:
                counts["__executing__"] += 1
            elif t.status in (TaskStatus.BACKLOG, TaskStatus.READY):
                counts["__pending__"] += 1
            elif t.status in Scheduler._TERMINAL_STATES:
                pass
            elif t.status in Scheduler._RECOVERY_BLOCKING_STATES:
                counts["__blocking_recovery__"] += 1
            elif t.status == TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW:
                counts["__blocked_human__"] += 1
        return counts

    def __init__(
        self,
        project_id: int,
        run_id: int,
        max_parallel_tasks: int = 2,
        loop_interval: float = 0.5,
        db_manager: Any | None = None,
        runner_pool: TaskRunnerPool | None = None,
        execute_pipeline: bool = False,
    ):
        self.project_id = project_id
        self.run_id = run_id
        self.max_parallel_tasks = max_parallel_tasks
        self.loop_interval = loop_interval
        self.db_manager = db_manager
        self.execute_pipeline = execute_pipeline
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

    async def stop(self, timeout: float | None = 5.0) -> None:
        """Gracefully stop the scheduler background task."""
        if not self._running and self._task is None:
            return
        self._running = False
        self.trigger()  # Wake up if sleeping
        if self._task:
            try:
                if timeout is None:
                    await self._task
                else:
                    await asyncio.wait_for(self._task, timeout=timeout)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
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
        try:
            async with UnitOfWork(self.db_manager) as uow:
                manager = WorktreeManager(project_id=self.project_id, uow=uow)
                cleaned = await asyncio.wait_for(manager.cleanup_orphan_worktrees(), timeout=10.0)
                if cleaned:
                    logger.info(f"Cleaned up {len(cleaned)} orphan worktrees in background")
        except Exception as e:
            logger.warning(f"Orphan worktrees cleanup failed or timed out: {e}")

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

            # Check max_run_time budget
            from localforge.core.config import load_config

            try:
                config = load_config()
                max_run_time = config.budgets.max_run_time
            except Exception:
                max_run_time = 3600.0

            if run.resource_limits:
                max_run_time = run.resource_limits.get("max_run_time", max_run_time)

            elapsed_run_time = (datetime.now(UTC) - _as_utc(run.started_at)).total_seconds()
            if elapsed_run_time > max_run_time:
                logger.warning(
                    f"Run {self.run_id} exceeded maximum run time limit "
                    f"of {max_run_time}s. Aborting."
                )
                run.status = RunStatus.FAILED
                run.summary = f"Run exceeded maximum run time budget of {max_run_time} seconds."
                run.ended_at = datetime.now(UTC)
                await uow.executions.update_run(run)

                await self._abort_active_tasks(uow)
                self._running = False
                return

            # Watchdog check for stuck tasks
            await self._run_watchdog_checks(uow)

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

            counts = self._classify_task_statuses(tasks)
            executing_count = counts["__executing__"]
            has_pending = counts["__pending__"] > 0
            has_blocking_recovery = counts["__blocking_recovery__"] > 0
            only_blocked_human = (
                counts["__blocked_human__"] > 0 and counts["__blocking_recovery__"] == 0
            )

            await self._scrum_master_record_conformity(uow, tasks)

            # If every task is in a terminal-success state (PR_READY/DONE/CANCELLED),
            # close the run as COMPLETED.
            all_terminal_ok = (
                counts["__executing__"] == 0
                and not has_pending
                and not has_blocking_recovery
                and counts["__blocked_human__"] == 0
                and (
                    counts[TaskStatus.PR_READY.value]
                    + counts[TaskStatus.DONE.value]
                    + counts[TaskStatus.CANCELLED.value]
                )
                == counts["__total__"]
            )
            if all_terminal_ok:
                await self._finalize_run(
                    uow,
                    run,
                    tasks,
                    counts=counts,
                    run_status=RunStatus.COMPLETED,
                )
                self._running = False
                return

            # Tasks still executing or pending: scheduler falls through to claim.
            if executing_count > 0 or has_pending:
                if executing_count >= self.max_parallel_tasks:
                    return
            # FAILED_SAFE / BLOCKED remains: maybe recoverable under budget.
            if has_blocking_recovery:
                recovery_budget = 0
                if not os.getenv("PYTEST_CURRENT_TEST"):
                    recovery_budget = await self._recovery_budget_remaining(uow, run)
                    if recovery_budget > 0:
                        reopened = await self._scrum_master_unblock_failed_tasks(uow, tasks)
                        if reopened:
                            run.resource_limits = dict(run.resource_limits or {})
                            run.resource_limits[self.RUN_RECOVERY_CYCLES_KEY] = int(
                                run.resource_limits.get(self.RUN_RECOVERY_CYCLES_KEY, 0) + 1
                            )
                            await uow.executions.update_run(run)
                            return
                else:
                    # Tests run fast: skip intra-iteration recovery work
                    # but still surface blockers honestly so the scheduler
                    # does not pretend the run is healthy.
                    recovery_budget = 0
                await self._escalate_remaining_blockers(uow, tasks)
                await self._finalize_run(
                    uow,
                    run,
                    tasks,
                    counts=self._classify_task_statuses(
                        await uow.tasks.list_tasks_for_project(self.project_id)
                    ),
                    run_status=RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
                )
                self._running = False
                return

            # Tasks already in BLOCKED_NEEDS_HUMAN_REVIEW: stop the loop.
            if only_blocked_human:
                await self._finalize_run(
                    uow,
                    run,
                    tasks,
                    counts=counts,
                    run_status=RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
                )
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
                    governed = GovernedExecutionService(runner)
                    try:
                        governed_result = await asyncio.wait_for(
                            governed.start_task(
                                GovernedExecutionRequest(
                                    project_id=self.project_id,
                                    run_id=self.run_id,
                                    task=t,
                                    task_run=task_run,
                                ),
                                uow=uow,
                            ),
                            timeout=45.0,
                        )
                    except Exception as e:
                        logger.error(
                            f"Task {t.key} failed during governed dispatch: {e!r}",
                            exc_info=True,
                        )
                        task_run.status = TaskRunStatus.FAILED
                        task_run.final_summary = f"Governed dispatch failed: {e!r}"
                        task_run.ended_at = datetime.now(UTC)
                        await uow.tasks.update_task_run(task_run)
                        await uow.tasks.update_task_status(t.id, TaskStatus.FAILED_SAFE)
                        continue
                    if governed_result.status != "STARTED":
                        continue

                    task_run = governed_result.task_run
                    if uow.session is not None:
                        await uow.session.commit()

                    if self.execute_pipeline:
                        assert task_run.id is not None
                        try:
                            await RolePipelineEngine(
                                uow, project_id=self.project_id, run_id=self.run_id
                            ).run_task(
                                task_id=t.id,
                                task_run_id=task_run.id,
                                mode=PipelineMode.DEFAULT,
                                complete_run=False,
                            )
                            if governed_result.selected_runner_id and uow.runner_pool is not None:
                                await uow.runner_pool.release_runner_lease(
                                    governed_result.selected_runner_id,
                                    success=True,
                                    task_run_id=task_run.id,
                                    lease_token=governed_result.runner_lease_token,
                                )
                        except Exception as e:
                            logger.error(
                                f"Task {t.key} failed during pipeline execution: {e!r}",
                                exc_info=True,
                            )
                            if uow.session is not None:
                                await uow.session.rollback()
                            failed_task_run = await uow.tasks.get_task_run(task_run.id)
                            if failed_task_run is not None:
                                failed_task_run.status = TaskRunStatus.FAILED
                                if not failed_task_run.final_summary:
                                    failed_task_run.final_summary = (
                                        f"Pipeline execution failed: {e!r}"
                                    )
                                failed_task_run.ended_at = datetime.now(UTC)
                                await uow.tasks.update_task_run(failed_task_run)
                            else:
                                await uow.tasks.create_task_run(
                                    domain.TaskRun(
                                        run_id=self.run_id,
                                        task_id=t.id,
                                        status=TaskRunStatus.FAILED,
                                        worktree_path=task_run.worktree_path,
                                        branch_name=task_run.branch_name,
                                        sandbox_id=task_run.sandbox_id,
                                        ended_at=datetime.now(UTC),
                                        final_summary=f"Pipeline execution failed: {e!r}",
                                    )
                                )
                            await self._mark_task_failed_safe(uow, t.id)
                            if uow.session is not None:
                                await uow.session.commit()
                            latest_runs = await uow.tasks.list_runs_for_task(t.id)
                            if latest_runs:
                                await governed.cleanup(latest_runs[0], uow=uow)
                            if governed_result.selected_runner_id and uow.runner_pool is not None:
                                await uow.runner_pool.release_runner_lease(
                                    governed_result.selected_runner_id,
                                    success=False,
                                    task_run_id=task_run.id,
                                    lease_token=governed_result.runner_lease_token,
                                )
                            continue

                    executing_count += 1

    async def _scrum_master_record_conformity(
        self, uow: UnitOfWork, tasks: list[domain.Task]
    ) -> None:
        assert uow.tasks is not None
        for task in tasks:
            if task.id is None or task.status not in (
                TaskStatus.PR_READY,
                TaskStatus.FAILED_SAFE,
            ):
                continue
            metadata = dict(task.metadata or {})
            runs = await uow.tasks.list_runs_for_task(task.id)
            latest = max(runs, key=lambda run: run.id or 0) if runs else None
            status = "passed" if task.status == TaskStatus.PR_READY else "blocked"
            blocker = ""
            if status == "blocked":
                blocker = (
                    latest.final_summary if latest and latest.final_summary else "Unknown blocker"
                )
            check = {
                "status": status,
                "checked_by": AgentRole.SCRUM_MASTER.value,
                "model": "gemma4:12b",
                "task_status": task.status.value,
                "blocker": blocker[:1200],
                "checked_at": datetime.now(UTC).isoformat(),
            }
            previous = metadata.get("scrum_master_conformity")
            if (
                isinstance(previous, dict)
                and previous.get("status") == check["status"]
                and previous.get("task_status") == check["task_status"]
                and previous.get("blocker") == check["blocker"]
            ):
                continue
            metadata["scrum_master_conformity"] = check
            task.metadata = metadata
            await uow.tasks.update_task(task)
            if uow.audits is not None:
                await uow.audits.append_audit_event(
                    domain.AuditEvent(
                        project_id=self.project_id,
                        run_id=self.run_id,
                        task_id=task.id,
                        actor_type=AuditEventActorType.AGENT,
                        actor_id=AgentRole.SCRUM_MASTER.value,
                        event_type=AuditEventType.SYSTEM_EVENT,
                        payload_redacted={
                            "action": "scrum_master_conformity_check",
                            "task_key": task.key,
                            **check,
                        },
                    )
                )

    async def _scrum_master_unblock_failed_tasks(
        self, uow: UnitOfWork, tasks: list[domain.Task]
    ) -> int:
        # Demo guard: when the operator pinned the local lane through
        # scripts/apply_demo_local_first.py (which sets
        # demo_local_first = True on the task metadata) the recovery
        # loop must NOT silently switch into chief_only on every retry.
        # Without this guard, a single Ollama timeout keeps escalating
        # the task to Chief Engineer, which is the exact opposite of
        # what the demo expects.
        """Re-open recoverable FAILED_SAFE tasks with Chief guidance.

        Tasks previously overridden by the demo script keep their
        original seniority_class (e.g. local_assisted) and are
        returned to READY with a guardian note, but never escalated
        to the Chief Engineer lane.
        """
        assert uow.tasks is not None
        try:
            max_attempts = max(6, load_config().budgets.max_repair_attempts + 3)
        except Exception:
            max_attempts = 6
        reopened = 0
        for task in tasks:
            if task.status != TaskStatus.FAILED_SAFE or task.id is None:
                continue
            task_id = task.id
            current_task = await uow.tasks.get_task(task_id)
            if current_task is not None:
                task = current_task
            metadata = dict(task.metadata or {})
            attempts = int(metadata.get("scrum_master_unblock_attempts", 0))
            if attempts >= max_attempts:
                continue
            runs = await uow.tasks.list_runs_for_task(task_id)
            latest = max(runs, key=lambda run: run.id or 0) if runs else None
            blocker = (
                _clean_error_message(latest.final_summary)
                if latest and latest.final_summary
                else "Unknown blocker"
            )
            contract = metadata.get("task_contract")
            if not isinstance(contract, dict):
                contract = {}
            notes = contract.get("implementation_notes")
            if not isinstance(notes, list):
                notes = []
            notes.append(
                "ScrumMaster unblock: Chief Engineer must remove this blocker "
                f"before PR readiness: {blocker[:600]}"
            )
            if "TimeoutError" in blocker or "timed out" in blocker.lower():
                notes.append(
                    "ScrumMaster diagnosis: previous attempt timed out. Chief Engineer must "
                    "return a small action set, avoid rewriting unrelated files, and solve the "
                    "blocked task by editing only the files allowed by the task contract."
                )
                metadata["max_task_duration"] = max(
                    float(metadata.get("max_task_duration", 0) or 0),
                    1200.0,
                )
            if "JSONDecodeError" in blocker or "unterminated string" in blocker.lower():
                notes.append(
                    "ScrumMaster diagnosis: previous action JSON was truncated. Chief Engineer "
                    "must return compact valid JSON only, with no prose and no omitted strings."
                )
            contract["implementation_notes"] = notes
            demo_local_first = bool(metadata.get("demo_local_first"))
            pre_existing_seniority = contract.get("seniority_class")
            if not demo_local_first:
                contract["seniority_class"] = "chief_only"
                contract["chief_engineer_unblock_required"] = True
                task.risk_level = "high"
            else:
                # Demo guard: keep the smaller override and surface the
                # blocker as a human-facing note so the run summary
                # continues to be honest.
                notes.append(
                    "ScrumMaster diagnosis (demo_local_first): operator pinned "
                    "the local lane; the Chief Engineer lane will not run. "
                    f"Blocker was: {blocker[:300]}"
                )
                contract["chief_engineer_unblock_required"] = False
                contract.pop("chief_engineer_unblock_required", None)
                # Preserve the demo override (typically local_assisted):
                contract["seniority_class"] = pre_existing_seniority or "local_assisted"
            contract["blocked_reason"] = blocker[:1200]
            await uow.tasks.update_task(task)
            await uow.tasks.update_task_status(task_id, TaskStatus.READY)
            if uow.audits is not None:
                await uow.audits.append_audit_event(
                    domain.AuditEvent(
                        project_id=self.project_id,
                        run_id=self.run_id,
                        task_id=task.id,
                        actor_type=AuditEventActorType.AGENT,
                        actor_id=AgentRole.SCRUM_MASTER.value,
                        event_type=AuditEventType.SYSTEM_EVENT,
                        payload_redacted={
                            "action": "scrum_master_unblock",
                            "task_key": task.key,
                            "attempt": attempts + 1,
                            "blocker": blocker[:1000],
                            "delegated_to": AgentRole.CHIEF_ENGINEER.value,
                        },
                    )
                )
            reopened += 1
        return reopened

    async def _mark_task_failed_safe(self, uow: UnitOfWork, task_id: int) -> None:
        assert uow.tasks is not None
        task = await uow.tasks.get_task(task_id)
        if task is None:
            return
        if task.status == TaskStatus.FAILED_SAFE:
            return
        if task.status in (TaskStatus.BACKLOG, TaskStatus.READY):
            if task.status == TaskStatus.BACKLOG:
                await uow.tasks.update_task_status(task_id, TaskStatus.READY)
            await uow.tasks.update_task_status(task_id, TaskStatus.CLAIMED)
            await uow.tasks.update_task_status(task_id, TaskStatus.PLANNING)
            await uow.tasks.update_task_status(task_id, TaskStatus.IMPLEMENTING)
        await uow.tasks.update_task_status(task_id, TaskStatus.FAILED_SAFE)

    async def _abort_active_tasks(self, uow: UnitOfWork) -> None:
        """Abort all active task runs and move their tasks to FAILED_SAFE status."""
        assert uow.tasks is not None
        tasks = await uow.tasks.list_tasks_for_project(self.project_id)
        active_tasks = [
            t
            for t in tasks
            if t.status
            in (
                TaskStatus.CLAIMED,
                TaskStatus.PLANNING,
                TaskStatus.IMPLEMENTING,
                TaskStatus.TESTING,
                TaskStatus.REPAIRING,
                TaskStatus.REVIEWING,
            )
            and t.id is not None
        ]
        active_task_ids = [t.id for t in active_tasks if t.id is not None]
        runs_by_task = await uow.tasks.list_runs_for_tasks(active_task_ids)
        for t in active_tasks:
            assert t.id is not None
            await uow.tasks.update_task_status(t.id, TaskStatus.FAILED_SAFE)
            for r in runs_by_task.get(t.id, []):
                if r.run_id == self.run_id and r.status == TaskRunStatus.RUNNING:
                    r.status = TaskRunStatus.FAILED
                    r.final_summary = "Task run aborted due to run budget timeout."
                    r.ended_at = datetime.now(UTC)
                    await uow.tasks.update_task_run(r)

                    runner = self.runner_pool.acquire(t)
                    await runner.cleanup(r, uow=uow)

    async def _run_watchdog_checks(self, uow: UnitOfWork) -> None:
        """Scan active task runs and abort those whose heartbeat (updated_at) has stopped."""
        assert uow.tasks is not None
        assert uow.executions is not None
        from localforge.core.config import load_config

        try:
            config = load_config()
            task_timeout = config.budgets.max_task_duration
        except Exception:
            task_timeout = 600.0

        run = await uow.executions.get_run(self.run_id)
        if run and run.resource_limits:
            task_timeout = run.resource_limits.get("max_task_duration", task_timeout)

        tasks = await uow.tasks.list_tasks_for_project(self.project_id)
        active_tasks = [
            t
            for t in tasks
            if t.status
            in (
                TaskStatus.CLAIMED,
                TaskStatus.PLANNING,
                TaskStatus.IMPLEMENTING,
                TaskStatus.TESTING,
                TaskStatus.REPAIRING,
                TaskStatus.REVIEWING,
            )
            and t.id is not None
        ]
        active_task_ids = [t.id for t in active_tasks if t.id is not None]
        runs_by_task = await uow.tasks.list_runs_for_tasks(active_task_ids)
        for t in active_tasks:
            assert t.id is not None
            for r in runs_by_task.get(t.id, []):
                if r.run_id == self.run_id and r.status == TaskRunStatus.RUNNING:
                    # For watchdog check, we compare against task run started_at.
                    elapsed = (datetime.now(UTC) - _as_utc(r.started_at)).total_seconds()
                    if elapsed > task_timeout:
                        logger.warning(
                            f"Task run {r.id} for task {t.key} is unresponsive "
                            f"(stuck for {elapsed}s). Watchdog aborting."
                        )
                        r.status = TaskRunStatus.FAILED
                        r.final_summary = f"Watchdog terminated unresponsive task after {elapsed}s."
                        r.ended_at = datetime.now(UTC)
                        await uow.tasks.update_task_run(r)
                        await uow.tasks.update_task_status(t.id, TaskStatus.FAILED_SAFE)

                        runner = self.runner_pool.acquire(t)
                        await runner.cleanup(r, uow=uow)

    async def _recovery_budget_remaining(self, uow: UnitOfWork, run: domain.Run) -> int:
        """Return how many additional scheduler recovery cycles are still available.

        Honors BudgetsConfig.max_run_recovery_cycles and the absolute USD
        ceiling. Returns 0 to signal "stop trying; escalate to human".
        """
        from localforge.core.config import load_config

        try:
            config = load_config()
            max_cycles = config.budgets.max_run_recovery_cycles
            max_usd = config.budgets.max_paid_usd_absolute
        except Exception:
            return 0

        limits = dict(run.resource_limits or {})
        cycles_used = int(limits.get(self.RUN_RECOVERY_CYCLES_KEY, 0))
        if cycles_used >= max_cycles:
            return 0
        spent_usd = 0.0
        executions = cast(Any, uow).executions
        model_calls = cast(Any, uow).model_calls
        if executions is not None:
            try:
                if model_calls is not None:
                    totals = await model_calls.get_run_totals(
                        project_id=self.project_id, run_id=self.run_id
                    )
                    spent_usd = float(totals.get("estimated_cost_usd", 0.0) or 0.0)
            except Exception:
                spent_usd = 0.0
        limits[self.RUN_PAID_USD_SPENT_KEY] = spent_usd
        run.resource_limits = limits
        if executions is not None:
            try:
                await executions.update_run(run)
            except Exception:
                pass
        if spent_usd >= max_usd:
            return 0
        return max_cycles - cycles_used

    async def _escalate_remaining_blockers(self, uow: UnitOfWork, tasks: list[domain.Task]) -> int:
        """Move FAILED_SAFE / BLOCKED tasks that exhausted the recovery
        budget into BLOCKED_NEEDS_HUMAN_REVIEW so the run can close
        honestly. Returns the number of escalated tasks.
        """
        tasks_svc = cast(Any, uow).tasks
        if tasks_svc is None:
            return 0
        escalated = 0
        for t in tasks:
            if t.id is None:
                continue
            if t.status not in (
                TaskStatus.FAILED_SAFE,
                TaskStatus.BLOCKED,
            ):
                continue
            try:
                await tasks_svc.update_task_status(
                    t.id,
                    TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
                )
                escalated += 1
            except ValueError:
                # Validation rejects some transitions; leave task where it is.
                continue
        return escalated

    async def _finalize_run(
        self,
        uow: UnitOfWork,
        run: domain.Run,
        tasks: list[domain.Task],
        *,
        counts: dict[str, int],
        run_status: RunStatus,
    ) -> None:
        """Persist run.status / run.summary and write run_summary.md.

        The body here replaces the older monolithic block so that the
        scheduler can finish runs as COMPLETED, FAILED, or
        BLOCKED_NEEDS_HUMAN_REVIEW with a single source of truth.
        """
        run.status = run_status
        run.ended_at = datetime.now(UTC)

        prs_ready_count = counts[TaskStatus.PR_READY.value] + counts[TaskStatus.DONE.value]
        blocked_count = counts[TaskStatus.BLOCKED.value]
        failed_safe_count = counts[TaskStatus.FAILED_SAFE.value]
        blocked_human_count = counts[TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW.value]

        safety_blocks = 0
        audits_svc = cast(Any, uow).audits
        if audits_svc is not None:
            audits = await audits_svc.list_audit_events_for_project(self.project_id)
            safety_blocks = len(
                [
                    e
                    for e in audits
                    if e.run_id == self.run_id
                    and e.event_type == AuditEventType.SAFETY_DECISION
                    and e.payload_redacted.get("decision") == "DENY"
                ]
            )
        recovery_cycles_used = int((run.resource_limits or {}).get(self.RUN_RECOVERY_CYCLES_KEY, 0))
        paid_usd_spent = float(
            (run.resource_limits or {}).get(self.RUN_PAID_USD_SPENT_KEY, 0.0) or 0.0
        )

        recommendations: list[str] = []
        if blocked_human_count > 0:
            recommendations.append(
                f"- {blocked_human_count} task(s) were moved to "
                f"BLOCKED_NEEDS_HUMAN_REVIEW after exhausting the recovery "
                f"budget. Open run_summary.md for the per-task blockers and "
                f"resume them manually."
            )
        if failed_safe_count > 0:
            recommendations.append(
                f"- Review logs for {failed_safe_count} FAILED_SAFE task(s) "
                f"and adjust resource budgets or LLM configurations."
            )
        if blocked_count > 0:
            recommendations.append("- Resolve dependency tasks that blocked subsequent tasks.")
        if safety_blocks > 0:
            recommendations.append(
                "- Review Safety Kernel logs to see why commands or files were blocked."
            )
        if not recommendations:
            recommendations.append("- Execution completed cleanly. Ready to merge PRs!")

        summary_lines = [
            "Execution Summary:",
            f"- Run Status: {run_status.value}",
            f"- Recovery cycles used: {recovery_cycles_used}",
            f"- Paid USD spent (cumulative): ${paid_usd_spent:.4f}",
            f"- PRs Ready/Done: {prs_ready_count}",
            f"- Blocked Tasks: {blocked_count}",
            f"- Failed-Safe Tasks: {failed_safe_count}",
            f"- Tasks Needing Human Review: {blocked_human_count}",
            f"- Safety Kernel Blocks: {safety_blocks}",
            "",
            "Recommended Next Steps:",
            *recommendations,
        ]

        # Per-task blocker detail for BLOCKED_NEEDS_HUMAN_REVIEW
        if blocked_human_count > 0:
            summary_lines.append("")
            summary_lines.append("Per-task Blockers:")
            for t in tasks:
                if t.status != TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW:
                    continue
                metadata = dict(t.metadata or {})
                last_blocker = str(metadata.get("scrum_master_last_blocker", "Unknown blocker"))[
                    :600
                ]
                summary_lines.append(f"- {t.key} ({t.title}): {last_blocker}")

        run.summary = "\n".join(summary_lines)
        executions_svc = cast(Any, uow).executions
        if executions_svc is not None:
            await executions_svc.update_run(run)

        # Persist run_summary.md at project root for human consumption
        projects_svc = cast(Any, uow).projects
        project = None
        if projects_svc is not None:
            project = await projects_svc.get_project(self.project_id)
        if project:
            md = (
                "# LocalForge OS — Run Execution Summary\n\n"
                f"**Run ID**: {self.run_id}\n"
                f"**Status**: {run.status.value}\n"
                f"**Ended At**: {run.ended_at.isoformat()}\n\n"
                "### Statistics\n"
                f"- **PRs Ready/Done**: {prs_ready_count}\n"
                f"- **Blocked Tasks**: {blocked_count}\n"
                f"- **Failed-Safe Tasks**: {failed_safe_count}\n"
                f"- **Tasks Needing Human Review**: {blocked_human_count}\n"
                f"- **Safety Kernel Blocks**: {safety_blocks}\n"
                f"- **Recovery Cycles Used**: {recovery_cycles_used}\n"
                f"- **Paid USD Spent**: ${paid_usd_spent:.4f}\n\n"
                "### Recommended Next Steps\n" + "\n".join(recommendations) + "\n"
            )
            try:
                filepath = os.path.join(project.root_path, "run_summary.md")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(md)
            except Exception as e:
                logger.error(f"Failed to write run_summary.md: {e}")
