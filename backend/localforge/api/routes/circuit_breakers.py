from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import CircuitBreakerResetRequest, KillRunRequest
from localforge.models import domain
from localforge.models.enums import CircuitScope
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["circuit_breakers"])


@router.get("/projects/{project_id}/circuit-breakers")
async def list_circuit_breakers(project_id: int) -> list[domain.CircuitBreakerState]:
    """List all circuit breaker states for a project."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.circuit_breakers is not None
        return await uow.circuit_breakers.list_breakers_for_project(project_id)


@router.post("/projects/{project_id}/circuit-breakers/reset")
async def reset_circuit_breaker(project_id: int, req: CircuitBreakerResetRequest) -> domain.CircuitBreakerState:
    """Manually reset a circuit breaker to CLOSED state."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.circuit_breakers is not None
        try:
            scope_enum = CircuitScope(req.scope.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid CircuitScope: {req.scope}")

        return await uow.circuit_breakers.reset_breaker(
            project_id=project_id,
            scope=scope_enum,
            target_id=req.target_id,
            actor_id=req.actor_id,
            reason=req.reason,
        )


@router.post("/loop-runs/{run_id}/kill")
async def kill_loop_run(run_id: int, req: KillRunRequest) -> domain.LoopRun:
    """Kill an active or triaging Loop Run."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loop_coordinator is not None
        try:
            return await uow.loop_coordinator.kill_loop_run(
                run_id=run_id,
                actor_id=req.actor_id,
                reason=req.reason,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
