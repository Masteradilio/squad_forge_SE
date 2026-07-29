from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import SwarmCreateRequest
from localforge.models import domain
from localforge.models.enums import SwarmNodeType, SwarmStrategy, TypedArtifactType
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["light-swarm"])


def _build_nodes(req_nodes: list[Any]) -> list[domain.SwarmNode]:
    nodes: list[domain.SwarmNode] = []
    for n in req_nodes:
        nodes.append(
            domain.SwarmNode(
                node_id=n.node_id,
                node_type=SwarmNodeType(n.node_type),
                title=n.title,
                description=n.description,
                depends_on=n.depends_on,
                required_input_artifact_type=(
                    TypedArtifactType(n.required_input_artifact_type)
                    if n.required_input_artifact_type
                    else None
                ),
                output_artifact_type=(
                    TypedArtifactType(n.output_artifact_type) if n.output_artifact_type else None
                ),
            )
        )
    return nodes


@router.post("/swarms", status_code=status.HTTP_201_CREATED)
async def create_swarm(req: SwarmCreateRequest) -> dict[str, Any]:
    """Create a validated SwarmPlan and optionally start execution."""
    nodes = _build_nodes(req.nodes)
    policy = domain.SwarmPolicy(**req.policy.model_dump())
    edges: list[tuple[str, str]] = [tuple(e) for e in req.edges]  # type: ignore[misc]

    async with UnitOfWork(db_manager) as uow:
        assert uow.light_swarm is not None
        try:
            plan = await uow.light_swarm.create_plan(
                project_id=req.project_id,
                task_run_id=req.task_run_id,
                nodes=nodes,
                edges=edges,
                policy=policy,
                strategy=SwarmStrategy(req.strategy),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        run = None
        if req.auto_start and plan.id is not None:
            run = await uow.light_swarm.start_swarm(plan.id)

        return {
            "plan_id": plan.id,
            "run_id": run.id if run else None,
            "status": run.status if run else "DRAFT",
        }


@router.get("/swarms/{run_id}")
async def get_swarm_status(run_id: int) -> dict[str, Any]:
    """Get the current status of a SwarmRun."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.light_swarm is not None
        try:
            return await uow.light_swarm.get_dag_view(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/swarms/{run_id}/dag")
async def get_swarm_dag(run_id: int) -> dict[str, Any]:
    """Get the full DAG view for observability — nodes, edges, cost, tokens, wait time."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.light_swarm is not None
        try:
            return await uow.light_swarm.get_dag_view(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/swarms/{run_id}/summary")
async def get_swarm_summary(run_id: int) -> domain.SwarmExecutionSummary:
    """Get the replayable SwarmExecutionSummary for a completed run."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.light_swarm is not None
        try:
            return await uow.light_swarm.aggregate_result(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/swarms/{run_id}/pause")
async def pause_swarm(run_id: int) -> dict[str, Any]:
    """Pause a running swarm at swarm scope."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.light_swarm is not None
        try:
            run = await uow.light_swarm.pause_swarm(run_id)
            return {"run_id": run_id, "status": run.status}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/swarms/{run_id}/kill")
async def kill_swarm(run_id: int) -> dict[str, Any]:
    """Kill a swarm — all active nodes are released."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.light_swarm is not None
        try:
            run = await uow.light_swarm.kill_swarm(run_id)
            return {"run_id": run_id, "status": run.status, "verdict": run.verdict}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
