from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from localforge.models import domain
from localforge.models.enums import GraphMutationType
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["task-graph"])


class MutationRequest(BaseModel):
    mutation_type: str
    actor_agent_id: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_graph_version: int
    deep_swarm_run_id: int


class DeepSwarmPolicyInput(BaseModel):
    enabled: bool = False
    max_depth: int = 3
    max_nodes: int = 20
    max_fan_out: int = 6
    max_concurrent_workers: int = 4
    max_mutations: int = 50
    max_paid_calls: int = 100
    max_duration_seconds: int = 7200
    max_cost_usd: float = 20.0
    prefer_light_swarm: bool = True
    registered_decision_contract_ids: list[str] = Field(default_factory=list)
    stall_tick_threshold: int = 5


class DeepSwarmCreateRequest(BaseModel):
    plan_id: int
    policy: DeepSwarmPolicyInput = Field(default_factory=DeepSwarmPolicyInput)


class TickRequest(BaseModel):
    completed_node_ids: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    tokens: int = 0
    paid_calls: int = 0


class SideEffectRequest(BaseModel):
    node_id: str
    idempotency_key: str


# ─── Graph Versioning ──────────────────────────────────────────────────────── #


@router.post("/graph/{plan_id}/init", status_code=status.HTTP_201_CREATED)
async def init_graph(plan_id: int) -> dict[str, Any]:
    """Create the initial (version 0) graph snapshot for a plan (V6-900)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            gv = await uow.task_graph.create_initial_graph_version(plan_id)
            return {"plan_id": plan_id, "version": gv.version, "content_hash": gv.content_hash}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/graph/{plan_id}/latest")
async def get_latest_graph(plan_id: int) -> dict[str, Any]:
    """Get the latest graph version for a plan."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        gv = await uow.task_graph.get_latest_graph_version(plan_id)
        if not gv:
            raise HTTPException(
                status_code=404, detail=f"No graph version found for plan {plan_id}."
            )
        return {
            "plan_id": gv.plan_id,
            "version": gv.version,
            "content_hash": gv.content_hash,
            "node_count": len(gv.nodes_snapshot_json),
            "edge_count": len(gv.edges_snapshot_json),
            "nodes": gv.nodes_snapshot_json,
            "edges": gv.edges_snapshot_json,
        }


@router.get("/graph/{plan_id}/journal")
async def get_mutation_journal(plan_id: int) -> list[dict[str, Any]]:
    """Return the full append-only mutation journal for a plan (V6-900)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        journal = await uow.task_graph.get_mutation_journal(plan_id)
        return [
            {
                "id": m.id,
                "graph_version": m.graph_version,
                "parent_graph_version": m.parent_graph_version,
                "mutation_type": m.mutation_type,
                "actor_agent_id": m.actor_agent_id,
                "reason": m.reason,
                "content_hash": m.content_hash,
                "created_at": m.created_at.isoformat(),
            }
            for m in journal
        ]


@router.post("/graph/{plan_id}/mutate", status_code=status.HTTP_201_CREATED)
async def apply_mutation(plan_id: int, req: MutationRequest) -> dict[str, Any]:
    """Apply a validated mutation to the task graph (V6-901)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            mutation_type = GraphMutationType(req.mutation_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"Unknown mutation_type: {req.mutation_type}"
            ) from exc
        try:
            mutation, new_gv = await uow.task_graph.apply_mutation(
                plan_id=plan_id,
                mutation_type=mutation_type,
                actor_agent_id=req.actor_agent_id,
                reason=req.reason,
                payload=req.payload,
                expected_graph_version=req.expected_graph_version,
                deep_swarm_run_id=req.deep_swarm_run_id,
            )
            return {
                "mutation_id": mutation.id,
                "new_graph_version": new_gv.version,
                "content_hash": new_gv.content_hash,
            }
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/graph/{plan_id}/reconcile")
async def reconcile_graph(plan_id: int) -> dict[str, Any]:
    """Reconcile graph after a crash — resets RUNNING nodes to PENDING (V6-904)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            return await uow.task_graph.reconcile_after_restart(plan_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


# ─── Deep Swarm ─────────────────────────────────────────────────────────────── #


@router.post("/deep-swarms", status_code=status.HTTP_201_CREATED)
async def create_deep_swarm(req: DeepSwarmCreateRequest) -> dict[str, Any]:
    """Create a Deep Swarm run. Disabled by default (V6-903)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            policy = domain.DeepSwarmPolicy(**req.policy.model_dump())
            run = await uow.task_graph.create_deep_swarm_run(req.plan_id, policy)
            return {"run_id": run.id, "plan_id": run.plan_id, "status": run.status}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/deep-swarms/{run_id}/enable")
async def enable_deep_swarm(run_id: int) -> dict[str, Any]:
    """Opt-in to Deep Swarm execution (V6-903)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            run = await uow.task_graph.enable_deep_swarm(run_id)
            return {"run_id": run_id, "status": run.status}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/deep-swarms/{run_id}/tick")
async def tick_deep_swarm(run_id: int, req: TickRequest) -> dict[str, Any]:
    """Advance the deep swarm: stall detection, budget checks, node advancement (V6-903)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            run = await uow.task_graph.tick_deep_swarm(
                run_id,
                req.completed_node_ids,
                cost_usd=req.cost_usd,
                tokens=req.tokens,
                paid_calls=req.paid_calls,
            )
            return {
                "run_id": run_id,
                "status": run.status,
                "verdict": run.verdict,
                "stall_ticks": run.stall_ticks,
                "mutation_count": run.mutation_count,
                "cumulative_cost_usd": run.cumulative_cost_usd,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/deep-swarms/{run_id}/kill")
async def kill_deep_swarm(run_id: int) -> dict[str, Any]:
    """Kill a Deep Swarm run (V6-904)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            run = await uow.task_graph.kill_deep_swarm(run_id)
            return {"run_id": run_id, "status": run.status, "verdict": run.verdict}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/deep-swarms/{run_id}/side-effects/claim")
async def claim_side_effect(run_id: int, req: SideEffectRequest) -> dict[str, Any]:
    """Claim a stable external-action idempotency key."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            claimed = await uow.task_graph.claim_external_side_effect(
                run_id, req.node_id, req.idempotency_key
            )
            return {"run_id": run_id, "claimed": claimed}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/deep-swarms/{run_id}/side-effects/complete")
async def complete_side_effect(run_id: int, req: SideEffectRequest) -> dict[str, Any]:
    """Persist external-action completion for crash-safe replay."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.task_graph is not None
        try:
            run = await uow.task_graph.complete_external_side_effect(
                run_id, req.node_id, req.idempotency_key
            )
            return {"run_id": run_id, "status": run.status}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
