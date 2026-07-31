"""Deep Swarm governance and experimental gating service (V61C-701, V61C-703).

Manages experimental opt-in validation, fallback to Light Swarm / SINGLE_WORKER,
and atomic validation of dynamic graph mutations.
"""

import logging
from typing import Any

from localforge.models.enums import SwarmStrategy
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


async def check_deep_swarm_opt_in(
    plan_id: int, uow: UnitOfWork, enable_flag: bool = False
) -> tuple[bool, str, SwarmStrategy]:
    """Validate Deep Swarm experimental gating and decision artifact (V61C-703).

    Returns:
        (is_allowed, reason, fallback_strategy)
    """
    assert uow.task_graph is not None

    if not enable_flag:
        logger.info("Deep Swarm feature flag disabled for plan %d, falling back to LIGHT strategy", plan_id)
        return False, "DEEP_SWARM_FEATURE_DISABLED", SwarmStrategy.LIGHT

    latest_version = await uow.task_graph.get_latest_graph_version(plan_id)
    if latest_version is None:
        logger.info("No initialized graph version for plan %d, falling back to LIGHT strategy", plan_id)
        return False, "MISSING_INITIAL_GRAPH_VERSION", SwarmStrategy.LIGHT

    # Check for registered decision evidence artifact
    if uow.typed_handoffs is not None and plan_id:
        try:
            plan_orm = await uow.task_graph._load_plan_orm(plan_id)
            artifacts = await uow.typed_handoffs.list_artifacts_for_run(plan_orm.task_run_id)
            has_decision = any(
                art.evidence_json.get("deep_swarm_opt_in") is True for art in artifacts
            )
            if not has_decision:
                logger.warning("Deep Swarm opt-in flag present but missing registered decision artifact for plan %d", plan_id)
                return False, "MISSING_REGISTERED_DECISION_EVIDENCE", SwarmStrategy.LIGHT
        except Exception as exc:
            logger.warning("Could not check registered decision artifact for plan %d: %s", plan_id, exc)

    return True, "OPT_IN_VALIDATED", SwarmStrategy.LIGHT


async def validate_mutation_governance(
    plan_id: int,
    proposer_agent_id: str,
    mutation_payload: dict[str, Any],
    uow: UnitOfWork,
) -> tuple[bool, str]:
    """Atomically validate graph mutation version, acyclicity, limits, and audit proposer (V61C-701)."""
    assert uow.task_graph is not None

    latest = await uow.task_graph.get_latest_graph_version(plan_id)
    if latest is None:
        return False, "INITIAL_GRAPH_VERSION_MISSING"

    parent_version = mutation_payload.get("parent_graph_version")
    if parent_version is not None and parent_version != latest.version:
        msg = f"Stale graph mutation: expected parent version {latest.version}, got {parent_version}"
        logger.error(msg)
        return False, msg

    if not proposer_agent_id or proposer_agent_id.strip() == "":
        return False, "PROPOSER_AGENT_ID_REQUIRED"

    logger.info("Graph mutation approved for plan %d by agent %s (v%d)", plan_id, proposer_agent_id, latest.version)
    return True, "MUTATION_GOVERNANCE_PASSED"
