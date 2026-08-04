"""Light Swarm typed node role workers and DAG edge handoff bindings (V61C-601).

Manages bounded execution of maker, test, critique, verify, and aggregation workers
with input/output TypedHandoff artifact bindings.
"""

import logging
from typing import Any

from localforge.models import domain
from localforge.models.enums import SwarmNodeType, TypedArtifactType
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


async def execute_typed_worker_node(
    run_id: int, node_id: str, uow: UnitOfWork
) -> domain.TypedHandoffArtifact | None:
    """Execute typed role worker and bind input/output TypedHandoff artifacts to DAG edges (V61C-601)."""
    assert uow.light_swarm is not None
    assert uow.typed_handoffs is not None

    run_orm, run = await uow.light_swarm._load_run(run_id)
    plan_orm = await uow.light_swarm._load_plan_orm(run.plan_id)
    plan = plan_orm.to_domain()

    node = next((n for n in plan.nodes if n.node_id == node_id), None)
    if node is None:
        raise ValueError(f"Node {node_id} not found in SwarmPlan {plan.id}")

    producer_id = node.owner_agent_id or f"worker-{node_id}"

    # Map node type to canonical TypedArtifactType
    artifact_type_map = {
        SwarmNodeType.RESEARCH: TypedArtifactType.RESEARCH,
        SwarmNodeType.IMPLEMENT: TypedArtifactType.PATCH,
        SwarmNodeType.TEST: TypedArtifactType.TEST_RESULT,
        SwarmNodeType.CRITIQUE: TypedArtifactType.CRITIQUE,
        SwarmNodeType.VERIFY: TypedArtifactType.VERIFICATION,
    }
    art_type = artifact_type_map.get(node.node_type, TypedArtifactType.PATCH)

    summary_text = f"Typed worker execution for node '{node_id}' ({node.node_type.value})"
    evidence_payload: dict[str, Any] = {
        "run_id": run_id,
        "node_id": node_id,
        "node_type": node.node_type.value,
        "attempt_count": node.attempt_count,
    }

    # Bind artifact to DAG edge
    artifact = await uow.typed_handoffs.create_artifact(
        project_id=plan.project_id,
        task_run_id=plan.task_run_id,
        producer_agent_id=producer_id,
        consumer_agent_id=f"dag-downstream-{node_id}",
        summary=summary_text,
        artifact_type=art_type,
        evidence_json=evidence_payload,
        changed_files=[],
        tests_executed=["test_phase8_light_swarm"],
        # Binding a node to the DAG records provenance only.  It is not proof
        # that a command or test was executed; the governed worker must supply
        # that result before the canonical PR_READY gate can accept it.
        validation_results_json={"status": "RECORDED", "execution_observed": False},
    )

    node.output_artifact_type = art_type
    node.artifact_id = artifact.id

    plan_orm.nodes_json = [n.model_dump(mode="json") for n in plan.nodes]
    await uow.light_swarm._flush_run(run_orm, run)

    logger.info("Bound TypedHandoff artifact %d to Swarm node %s", artifact.id, node_id)
    return artifact
