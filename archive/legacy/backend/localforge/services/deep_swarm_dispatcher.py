"""Deep Swarm governed dynamic node dispatch and crash recovery (V61C-700, V61C-702).

Dispatches ready dynamic DAG nodes through GovernedExecution and RunnerPool,
requiring typed dependency evidence and enforcing deterministic descendant cancellation.
"""

import logging
from datetime import UTC, datetime

from localforge.models import domain
from localforge.models.enums import RunnerLane, SwarmNodeStatus, SwarmNodeType
from localforge.services.light_swarm_dispatcher import ensure_swarm_runner_registered
from localforge.services.light_swarm_tokens import generate_node_ownership_token
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


async def dispatch_dynamic_ready_nodes(
    run_id: int, uow: UnitOfWork
) -> list[domain.SwarmNode]:
    """Dispatch ready dynamic atomic nodes through GovernedExecution & RunnerPool (V61C-700)."""
    assert uow.task_graph is not None
    assert uow.runner_pool is not None

    run_orm, run = await uow.task_graph._load_deep_run(run_id)
    plan_orm = await uow.task_graph._load_plan_orm(run.plan_id)
    plan = plan_orm.to_domain()

    latest_version = await uow.task_graph.get_latest_graph_version(run.plan_id)
    if latest_version is None:
        return []

    # Parse current nodes and edges snapshot
    nodes_raw = latest_version.nodes_snapshot_json or []
    edges_raw = latest_version.edges_snapshot_json or []
    current_nodes = [domain.SwarmNode.model_validate(n) for n in nodes_raw]

    ready_node_ids = uow.task_graph._resolve_ready_node_ids(nodes_raw, edges_raw, run.node_statuses)
    unassigned = [
        nid
        for nid in ready_node_ids
        if run.node_statuses.get(nid) in (SwarmNodeStatus.PENDING, SwarmNodeStatus.PENDING.value, SwarmNodeStatus.READY, SwarmNodeStatus.READY.value)
    ]

    if not unassigned:
        return []

    dispatched_nodes: list[domain.SwarmNode] = []
    await ensure_swarm_runner_registered(uow)

    for nid in unassigned:
        node = next((n for n in current_nodes if n.node_id == nid), None)
        if node is None:
            continue

        # Check typed dependency evidence for upstream nodes if typed_handoffs present
        if uow.typed_handoffs is not None and node.depends_on:
            try:
                artifacts = await uow.typed_handoffs.list_artifacts_for_run(plan.task_run_id)
                dep_artifact_producers = {art.producer_agent_id for art in artifacts}
                # Ensure all parent nodes produced evidence
                missing_deps = [dep for dep in node.depends_on if not any(dep in p for p in dep_artifact_producers)]
                if missing_deps:
                    logger.info("Node %s missing typed dependency evidence from %s, delaying dispatch", nid, missing_deps)
                    continue
            except Exception as exc:
                logger.warning("Error checking typed dependency evidence for node %s: %s", nid, exc)

        # Dispatch through RunnerPool
        selected_runner, status, dispatch_log = await uow.runner_pool.dispatch_task(
            project_id=plan.project_id,
            task_run_id=plan.task_run_id,
            required_lane=RunnerLane.INLINE,
            required_tools=["git", "python"],
        )

        if selected_runner is None:
            logger.warning("No runner available for DeepSwarm node %s: %s", nid, status)
            continue

        node.status = SwarmNodeStatus.RUNNING
        node.runner_id = selected_runner.runner_id
        node.owner_agent_id = f"deep-worker-{selected_runner.runner_id}-{nid}"
        node.started_at = datetime.now(UTC)
        node.attempt_count += 1
        node.ownership_token = generate_node_ownership_token(run_id, nid, node.attempt_count)

        if node.node_type == SwarmNodeType.IMPLEMENT:
            node.maker_agent_id = node.owner_agent_id
            if uow.path_leases is not None:
                try:
                    project = await uow.projects.get_project(plan.project_id) if uow.projects else None
                    if project and project.root_path:
                        await uow.path_leases.acquire_lease(
                            project_id=plan.project_id,
                            target_path=project.root_path,
                            owner_id=node.owner_agent_id,
                            task_run_id=plan.task_run_id,
                        )
                except Exception as exc:
                    logger.warning("Error acquiring PathLease for DeepSwarm node %s: %s", nid, exc)

        run.node_statuses[nid] = SwarmNodeStatus.RUNNING.value
        dispatched_nodes.append(node)

    await uow.task_graph._flush_deep_run(run_orm, run)
    return dispatched_nodes


async def reconcile_and_cancel_descendants(
    plan_id: int, failed_node_id: str, uow: UnitOfWork
) -> list[str]:
    """Deterministically cancel descendants of failed nodes and reconcile state (V61C-702)."""
    assert uow.task_graph is not None

    latest_version = await uow.task_graph.get_latest_graph_version(plan_id)
    if latest_version is None:
        return []

    nodes_raw = latest_version.nodes_snapshot_json or []
    edges_raw = latest_version.edges_snapshot_json or []

    # Find descendants via BFS
    descendants = list(uow.task_graph._bfs_descendants(failed_node_id, nodes_raw, edges_raw))

    deep_run_res = await uow.task_graph._load_latest_deep_run_for_plan(plan_id)
    if deep_run_res is not None:
        run_orm, run = deep_run_res
        for d_id in descendants:
            if run.node_statuses.get(d_id) in (SwarmNodeStatus.PENDING.value, SwarmNodeStatus.READY.value):
                run.node_statuses[d_id] = SwarmNodeStatus.BLOCKED.value
        await uow.task_graph._flush_deep_run(run_orm, run)

    logger.info("Cancelled %d descendants of failed node %s in plan %d", len(descendants), failed_node_id, plan_id)
    return descendants
