from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import RunnerDispatchRequest, RunnerRegisterRequest
from localforge.models import domain
from localforge.models.enums import RunnerHealthState, RunnerLane
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["runners"])


@router.get("/runners")
async def list_runners() -> list[domain.RunnerPoolState]:
    """List all registered runners and their current states."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        return await uow.runner_pool.list_runners()


@router.post("/runners", status_code=status.HTTP_201_CREATED)
async def register_runner(req: RunnerRegisterRequest) -> domain.RunnerPoolState:
    """Register or update a runner in the RunnerPool."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        caps = domain.RunnerCapability(
            lane=RunnerLane(req.lane),
            tools=req.tools,
            supported_task_types=req.supported_task_types,
            max_concurrency=req.max_concurrency,
        )
        return await uow.runner_pool.register_runner(
            runner_id=req.runner_id,
            name=req.name,
            lane=RunnerLane(req.lane),
            capabilities=caps,
            max_concurrency=req.max_concurrency,
        )


@router.post("/runners/dispatch")
async def dispatch_runner(req: RunnerDispatchRequest) -> dict[str, Any]:
    """Perform capability-aware deterministic dispatch for a task run."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        lane_enum = RunnerLane(req.required_lane) if req.required_lane else None
        runner, status_str, log = await uow.runner_pool.dispatch_task(
            project_id=req.project_id,
            task_run_id=req.task_run_id,
            required_lane=lane_enum,
            required_tools=req.required_tools,
            required_task_type=req.required_task_type,
        )

        if not runner:
            raise HTTPException(
                status_code=409,
                detail=f"Dispatch failed with status '{status_str}'. Rejection reasons: {log.rejection_reasons_json}",
            )

        return {
            "dispatch_status": status_str,
            "selected_runner_id": runner.runner_id,
            "runner_name": runner.name,
            "active_tasks_count": runner.active_tasks_count,
        }


@router.post("/runners/{runner_id}/health")
async def update_runner_health(
    runner_id: str, health_state: str, quarantine_reason: str | None = None
) -> domain.RunnerPoolState:
    """Update health state of a runner."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.runner_pool is not None
        return await uow.runner_pool.update_runner_health(
            runner_id=runner_id,
            health_state=RunnerHealthState(health_state),
            quarantine_reason=quarantine_reason,
        )
