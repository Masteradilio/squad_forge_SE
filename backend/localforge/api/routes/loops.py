from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import LoopCreateRequest, LoopTriggerRequest
from localforge.models import domain
from localforge.models.enums import AutonomyLevel, ExecutionStrategy, LoopStatus, TriggerKind
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["loops"])


@router.post("/projects/{project_id}/loops", status_code=status.HTTP_201_CREATED)
async def create_loop(project_id: int, req: LoopCreateRequest) -> domain.LoopDefinition:
    """Create a new Loop Definition for a project."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None

        project = await uow.projects.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        try:
            trigger_k = TriggerKind(req.trigger_kind)
            exec_s = ExecutionStrategy(req.execution_strategy)
            auton_l = AutonomyLevel(req.autonomy)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid enum value: {exc}") from exc

        trigger = domain.LoopTrigger(
            kind=trigger_k,
            schedule=req.schedule,
            event_type=req.event_type,
        )

        loop_def = domain.LoopDefinition(
            project_id=project_id,
            name=req.name,
            repository_path=req.repository_path,
            enabled=req.enabled,
            trigger=trigger,
            detector=req.detector,
            execution_strategy=exec_s,
            autonomy=auton_l,
            max_budget_usd=req.max_budget_usd,
            safety_policy=req.safety_policy,
            escalation_policy=req.escalation_policy,
        )

        return await uow.loops.create_loop(loop_def)


@router.get("/projects/{project_id}/loops")
async def list_loops(project_id: int) -> list[domain.LoopDefinition]:
    """List all Loop Definitions for a project."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loops is not None
        return await uow.loops.list_loops_for_project(project_id)


@router.get("/loops/{loop_id}")
async def inspect_loop(loop_id: int) -> domain.LoopDefinition:
    """Get details of a Loop Definition."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loops is not None
        loop_def = await uow.loops.get_loop(loop_id)
        if not loop_def:
            raise HTTPException(status_code=404, detail=f"Loop {loop_id} not found")
        return loop_def


@router.put("/loops/{loop_id}/enable")
async def enable_loop(loop_id: int) -> domain.LoopDefinition:
    """Enable a Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loops is not None
        loop_def = await uow.loops.update_loop_status(loop_id, status=LoopStatus.IDLE, enabled=True)
        if not loop_def:
            raise HTTPException(status_code=404, detail=f"Loop {loop_id} not found")
        return loop_def


@router.put("/loops/{loop_id}/disable")
async def disable_loop(loop_id: int) -> domain.LoopDefinition:
    """Disable a Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loops is not None
        loop_def = await uow.loops.update_loop_status(
            loop_id, status=LoopStatus.DISABLED, enabled=False
        )

        if not loop_def:
            raise HTTPException(status_code=404, detail=f"Loop {loop_id} not found")
        return loop_def


@router.post("/loops/{loop_id}/pause")
async def pause_loop(loop_id: int) -> domain.LoopDefinition:
    """Pause an active Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loop_coordinator is not None
        try:
            return await uow.loop_coordinator.pause_loop(loop_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/loops/{loop_id}/resume")
async def resume_loop(loop_id: int) -> domain.LoopDefinition:
    """Resume a paused Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loop_coordinator is not None
        try:
            return await uow.loop_coordinator.resume_loop(loop_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/loops/{loop_id}/run-now")
async def run_loop_now(loop_id: int, req: LoopTriggerRequest | None = None) -> domain.LoopRun:
    """Trigger immediate execution of a Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loop_coordinator is not None
        trigger_k = TriggerKind(req.trigger_kind) if req else TriggerKind.MANUAL
        key = req.idempotency_key if req else None
        payload = req.payload if req else None

        try:
            return await uow.loop_coordinator.trigger_loop(
                loop_id=loop_id,
                trigger_kind=trigger_k,
                idempotency_key=key,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loops/{loop_id}/history")
async def list_loop_history(loop_id: int, limit: int = 50) -> list[domain.LoopRun]:
    """Get execution history for a Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loops is not None
        return await uow.loops.list_runs_for_loop(loop_id, limit=limit)


@router.get("/loops/{loop_id}/snapshot")
async def get_loop_snapshot(loop_id: int) -> domain.LoopStateSnapshot:
    """Get latest state snapshot for a Loop."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.loops is not None
        snapshot = await uow.loops.get_latest_snapshot(loop_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"No snapshot found for loop {loop_id}")
        return snapshot
