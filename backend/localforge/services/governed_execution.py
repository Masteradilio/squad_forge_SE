"""Canonical governed task execution spine for scheduler dispatch."""

from dataclasses import dataclass

from localforge.models import domain
from localforge.models.enums import RunnerLane, TaskRunStatus, TaskStatus
from localforge.services.runners import BaseTaskRunner, RunnerContext
from localforge.storage.transactions import UnitOfWork

DEFAULT_SCHEDULER_RUNNER_ID = "scheduler-local-worktree"


@dataclass(frozen=True)
class GovernedExecutionRequest:
    project_id: int
    run_id: int
    task: domain.Task
    task_run: domain.TaskRun
    required_lane: RunnerLane = RunnerLane.INLINE
    required_tools: tuple[str, ...] = ("git",)
    required_task_type: str | None = None


@dataclass(frozen=True)
class GovernedExecutionResult:
    status: str
    task_run: domain.TaskRun
    runner_context: RunnerContext | None = None
    selected_runner_id: str | None = None
    runner_lease_token: str | None = None
    dispatch_status: str | None = None
    rejection_reasons: dict[str, str] | None = None
    final_summary: str | None = None


class GovernedExecutionService:
    """Server-owned scheduler entrypoint for runner dispatch and worktree setup."""

    def __init__(self, physical_runner: BaseTaskRunner) -> None:
        self.physical_runner = physical_runner

    async def start_task(
        self, request: GovernedExecutionRequest, *, uow: UnitOfWork
    ) -> GovernedExecutionResult:
        assert uow.runner_pool is not None
        assert uow.tasks is not None
        await uow.runner_pool.register_runner(
            DEFAULT_SCHEDULER_RUNNER_ID,
            "Scheduler Local Worktree Runner",
            lane=RunnerLane.INLINE,
            capabilities=domain.RunnerCapability(
                lane=RunnerLane.INLINE,
                tools=["git", "pytest", "python"],
                supported_task_types=[],
                max_concurrency=4,
            ),
            max_concurrency=4,
        )

        if request.task_run.id is None:
            raise ValueError("Governed execution requires a persisted TaskRun.")
        task_run_id = request.task_run.id

        selected_runner, dispatch_status, dispatch_log = await uow.runner_pool.dispatch_task(
            project_id=request.project_id,
            task_run_id=task_run_id,
            required_lane=request.required_lane,
            required_tools=list(request.required_tools),
            required_task_type=request.required_task_type,
        )
        if selected_runner is None:
            request.task_run.status = TaskRunStatus.FAILED
            request.task_run.final_summary = (
                "Governed runner dispatch failed: "
                f"{dispatch_status}; {dispatch_log.rejection_reasons_json}"
            )
            await uow.tasks.update_task_run(request.task_run)
            if request.task.id is not None:
                await uow.tasks.update_task_status(request.task.id, TaskStatus.FAILED_SAFE)
            return GovernedExecutionResult(
                status="FAILED_CLOSED",
                task_run=request.task_run,
                dispatch_status=dispatch_status,
                rejection_reasons=dispatch_log.rejection_reasons_json,
                final_summary=request.task_run.final_summary,
            )

        try:
            runner_context = await self.physical_runner.setup(
                request.task,
                run_id=request.run_id,
                uow=uow,
            )
        except Exception as exc:
            await uow.runner_pool.release_runner_lease(
                selected_runner.runner_id,
                success=False,
                task_run_id=task_run_id,
                lease_token=dispatch_log.lease_token,
            )
            request.task_run.status = TaskRunStatus.FAILED
            request.task_run.final_summary = f"Runner setup failed: {exc!r}"
            await uow.tasks.update_task_run(request.task_run)
            if request.task.id is not None:
                await uow.tasks.update_task_status(request.task.id, TaskStatus.FAILED_SAFE)
            return GovernedExecutionResult(
                status="FAILED_CLOSED",
                task_run=request.task_run,
                selected_runner_id=selected_runner.runner_id,
                runner_lease_token=dispatch_log.lease_token,
                dispatch_status=dispatch_status,
                final_summary=request.task_run.final_summary,
            )

        request.task_run.worktree_path = runner_context.worktree_path
        request.task_run.branch_name = runner_context.branch_name
        request.task_run.sandbox_id = runner_context.sandbox_id
        await uow.tasks.update_task_run(request.task_run)
        if (
            uow.worktrees is not None
            and request.task.id is not None
            and runner_context.worktree_path
            and runner_context.branch_name
            and runner_context.source_commit
        ):
            raw_expected_paths = request.task.metadata.get("expected_paths") or request.task.metadata.get(
                "allowed_files"
            )
            expected_paths = raw_expected_paths if isinstance(raw_expected_paths, list) else []
            await uow.worktrees.create_attempt_manifest(
                project_id=request.project_id,
                task_id=request.task.id,
                task_run_id=task_run_id,
                worktree_path=runner_context.worktree_path,
                branch_name=runner_context.branch_name,
                source_commit=runner_context.source_commit,
                owner_agent_id=selected_runner.runner_id,
                expected_paths=[str(path) for path in expected_paths],
                attempt_number=request.task_run.attempt_count,
            )
        return GovernedExecutionResult(
            status="STARTED",
            task_run=request.task_run,
            runner_context=runner_context,
            selected_runner_id=selected_runner.runner_id,
            runner_lease_token=dispatch_log.lease_token,
            dispatch_status=dispatch_status,
        )

    async def cleanup(self, task_run: domain.TaskRun, *, uow: UnitOfWork) -> None:
        await self.physical_runner.cleanup(task_run, uow=uow)
