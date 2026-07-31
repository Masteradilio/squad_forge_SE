"""Light Swarm resource release and lifecycle cascade management (V61C-602).

Manages atomic release of PathLeases, RunnerPool capacity leases, and Worktree attempt
manifests when a swarm run is killed, paused, or fails.
"""

import logging
from datetime import UTC, datetime

from localforge.models import domain
from localforge.models.enums import CircuitScope, LeaseReleaseReason, SwarmNodeStatus, SwarmStatus
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


async def release_swarm_run_resources(
    run_id: int, uow: UnitOfWork, reason: str = "KILLED"
) -> None:
    """Release all RunnerPool leases, PathLeases, and cancel Worktree manifests for a swarm run (V61C-602)."""
    assert uow.light_swarm is not None

    run_orm, run = await uow.light_swarm._load_run(run_id)
    plan_orm = await uow.light_swarm._load_plan_orm(run.plan_id)
    plan = plan_orm.to_domain()

    active_nodes = [n for n in plan.nodes if n.node_id in run.active_node_ids]

    for node in active_nodes:
        node.status = SwarmNodeStatus.BLOCKED
        node.error_reason = reason
        node.finished_at = datetime.now(UTC)

        # Release PathLease if owner_agent_id was set
        if node.owner_agent_id and uow.path_leases is not None:
            try:
                active_leases = await uow.path_leases.list_active_leases(project_id=plan.project_id)
                for lease in active_leases:
                    if lease.owner_id == node.owner_agent_id and lease.id is not None:
                        await uow.path_leases.release_lease(
                            lease.id, owner_id=node.owner_agent_id, reason=LeaseReleaseReason.CANCELLED
                        )
                        logger.info("Released PathLease %d for swarm node %s", lease.id, node.node_id)
            except Exception as exc:
                logger.warning("Error releasing PathLease for node %s: %s", node.node_id, exc)

        # Release RunnerPool lease if runner_id was set
        if node.runner_id and uow.runner_pool is not None:
            try:
                dispatch_logs = await uow.runner_pool.list_dispatch_logs_for_task_run(plan.task_run_id)
                for log in dispatch_logs:
                    if log.selected_runner_id == node.runner_id and log.lease_token:
                        await uow.runner_pool.release_runner_lease(
                            runner_id=node.runner_id,
                            success=False,
                            task_run_id=plan.task_run_id,
                            lease_token=log.lease_token,
                        )
                        logger.info("Released RunnerPool lease for node %s on runner %s", node.node_id, node.runner_id)
            except Exception as exc:
                logger.warning("Error releasing RunnerPool lease for node %s: %s", node.node_id, exc)

    # Cancel Worktree attempt manifests for task_run if worktrees service present
    if uow.worktrees is not None and plan.task_run_id:
        try:
            cancelled_count = await uow.worktrees.cancel_manifests_for_task_run(plan.task_run_id)
            logger.info("Cancelled %d WorktreeAttemptManifests for task_run %d", cancelled_count, plan.task_run_id)
        except Exception as exc:
            logger.warning("Error cancelling worktree manifests for task_run %d: %s", plan.task_run_id, exc)

    run.status = SwarmStatus.KILLED if reason == "KILLED_BY_USER" else SwarmStatus.FAILED
    run.verdict = reason
    run.finished_at = datetime.now(UTC)
    for nid in list(run.active_node_ids):
        run.node_statuses[nid] = SwarmNodeStatus.BLOCKED.value
    run.active_node_ids = []

    plan_orm.nodes_json = [n.model_dump(mode="json") for n in plan.nodes]
    await uow.light_swarm._flush_run(run_orm, run)


async def recover_swarm_run(run_id: int, uow: UnitOfWork) -> domain.SwarmRun:
    """Reconstruct ready/running/blocked nodes from durable state after process restart (V61C-602)."""
    assert uow.light_swarm is not None

    run_orm, run = await uow.light_swarm._load_run(run_id)
    plan_orm = await uow.light_swarm._load_plan_orm(run.plan_id)
    plan = plan_orm.to_domain()

    if run.status != SwarmStatus.RUNNING:
        logger.info("SwarmRun %d is not in RUNNING status (%s), skipping restart recovery", run_id, run.status.value)
        return run

    ready_ids = uow.light_swarm._resolve_ready_nodes(plan.nodes, run.node_statuses)
    running_ids = [
        nid
        for nid, st in run.node_statuses.items()
        if st in (SwarmNodeStatus.RUNNING, SwarmNodeStatus.RUNNING.value)
    ]

    run.active_node_ids = list(set(ready_ids + running_ids))

    # Trigger circuit breaker log if there are repeated node failures
    if uow.circuit_breakers is not None and plan.project_id:
        try:
            failed_count = sum(
                1 for st in run.node_statuses.values() if st in (SwarmNodeStatus.FAILED, SwarmNodeStatus.FAILED.value)
            )
            if failed_count > 0:
                fp = domain.FailureFingerprint(
                    error_type="NodeFailure",
                    normalized_message="Node execution failed in LightSwarm",
                    fingerprint_hash="light_swarm_node_failure_hash",
                )
                await uow.circuit_breakers.record_failure(
                    project_id=plan.project_id,
                    scope=CircuitScope.RUN,
                    target_id=f"swarm-{run_id}",
                    fingerprint=fp,
                )
        except Exception as exc:
            logger.warning("Could not record circuit breaker failure: %s", exc)

    await uow.light_swarm._flush_run(run_orm, run)
    logger.info("Recovered SwarmRun %d state with %d active nodes", run_id, len(run.active_node_ids))
    return run

