"""Light Swarm governed node dispatch service (V61C-600).

Handles node attempt creation, RunnerPool capacity dispatch, Worktree isolation,
and PathLease reservation for executable DAG nodes.
"""

import logging
from datetime import UTC, datetime

from localforge.models import domain
from localforge.models.enums import RunnerLane, SwarmNodeStatus, SwarmNodeType
from localforge.services.light_swarm_tokens import generate_node_ownership_token
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)

DEFAULT_SWARM_RUNNER_ID = "swarm-local-worker"


async def ensure_swarm_runner_registered(uow: UnitOfWork) -> str:
    """Ensure at least one capability-aware local runner is registered in the pool."""
    assert uow.runner_pool is not None
    await uow.runner_pool.register_runner(
        runner_id=DEFAULT_SWARM_RUNNER_ID,
        name="Swarm Local Worker Pool Runner",
        lane=RunnerLane.INLINE,
        capabilities=domain.RunnerCapability(
            lane=RunnerLane.INLINE,
            tools=["git", "pytest", "python"],
            supported_task_types=[],
            max_concurrency=4,
        ),
        max_concurrency=4,
    )
    return DEFAULT_SWARM_RUNNER_ID


async def dispatch_ready_swarm_nodes(run_id: int, uow: UnitOfWork) -> list[domain.SwarmNode]:
    """Dispatch ready nodes through GovernedExecution and capability-aware RunnerPool (V61C-600)."""
    assert uow.light_swarm is not None
    assert uow.runner_pool is not None

    run_orm, run = await uow.light_swarm._load_run(run_id)
    plan_orm = await uow.light_swarm._load_plan_orm(run.plan_id)
    plan = plan_orm.to_domain()

    ready_ids = uow.light_swarm._resolve_ready_nodes(plan.nodes, run.node_statuses)
    unassigned_ready = [
        nid
        for nid in ready_ids
        if run.node_statuses.get(nid)
        in (SwarmNodeStatus.PENDING, SwarmNodeStatus.PENDING.value, SwarmNodeStatus.READY, SwarmNodeStatus.READY.value)
        and (
            next((n for n in plan.nodes if n.node_id == nid), None) is not None
            and next(n for n in plan.nodes if n.node_id == nid).runner_id is None
        )
    ]
    if not unassigned_ready:
        return []

    # Enforce concurrency bound (max_workers)
    running_count = len(
        [
            nid
            for nid, st in run.node_statuses.items()
            if st in (SwarmNodeStatus.RUNNING, SwarmNodeStatus.RUNNING.value)
        ]
    )
    max_workers = min(plan.policy.max_workers, 4)
    available_capacity = max(0, max_workers - running_count)
    if available_capacity == 0:
        logger.info("SwarmRun %d reached max concurrency ceiling (%d running)", run_id, running_count)
        return []

    nodes_to_dispatch = unassigned_ready[:available_capacity]
    dispatched_nodes: list[domain.SwarmNode] = []

    await ensure_swarm_runner_registered(uow)

    for nid in nodes_to_dispatch:
        node = next((n for n in plan.nodes if n.node_id == nid), None)
        if node is None or run.node_statuses.get(nid) == SwarmNodeStatus.RUNNING.value:
            continue

        # Dispatch attempt through RunnerPool
        selected_runner, status, dispatch_log = await uow.runner_pool.dispatch_task(
            project_id=plan.project_id,
            task_run_id=plan.task_run_id,
            required_lane=RunnerLane.INLINE,
            required_tools=["git", "python"],
        )

        if selected_runner is None:
            logger.warning("No compatible runner for Swarm node %s: %s", nid, status)
            continue

        node.status = SwarmNodeStatus.RUNNING
        node.runner_id = selected_runner.runner_id
        node.owner_agent_id = f"worker-{selected_runner.runner_id}-{nid}"
        node.started_at = datetime.now(UTC)
        node.attempt_count += 1
        node.ownership_token = generate_node_ownership_token(run_id, nid, node.attempt_count)

        if node.node_type == SwarmNodeType.IMPLEMENT:
            node.maker_agent_id = node.owner_agent_id

        # Acquire PathLease for IMPLEMENT nodes if path_leases service is present
        if node.node_type == SwarmNodeType.IMPLEMENT and uow.path_leases is not None:
            try:
                project = await uow.projects.get_project(plan.project_id) if uow.projects else None
                if project and project.root_path:
                    lease, status_lease, _reason = await uow.path_leases.acquire_lease(
                        project_id=plan.project_id,
                        target_path=project.root_path,
                        owner_id=node.owner_agent_id,
                        task_run_id=plan.task_run_id,
                    )
                    if lease and lease.id is not None:
                        logger.info("PathLease acquired for node %s on %s (lease_id=%s, status=%s)", nid, project.root_path, lease.id, status_lease)
            except Exception as exc:
                logger.warning("Could not acquire PathLease for node %s: %s", nid, exc)

        run.node_statuses[nid] = SwarmNodeStatus.RUNNING.value
        if nid not in run.active_node_ids:
            run.active_node_ids.append(nid)

        dispatched_nodes.append(node)

    plan_orm.nodes_json = [n.model_dump(mode="json") for n in plan.nodes]
    await uow.light_swarm._flush_run(run_orm, run)
    return dispatched_nodes
