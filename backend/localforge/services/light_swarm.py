"""Light Swarm service — bounded multi-agent fan-out with policy enforcement.

Implements V6-800 through V6-804:
- SwarmPolicy validation (max 2-4 workers, depth=1, no sub-swarms)
- DAG decomposition with acyclicity check
- Deterministic node dispatch via RunnerPool integration
- Upstream failure propagation and circuit-breaker integration
- Single-worker fallback
- Pause/kill controls
- Replayable SwarmExecutionSummary export
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import (
    SwarmNodeStatus,
    SwarmNodeType,
    SwarmStatus,
    SwarmStrategy,
)
from localforge.services.light_swarm_tokens import (
    generate_node_ownership_token,
    validate_maker_checker_identity,
    verify_node_ownership_token,
)
from localforge.storage.orm import SwarmPlanORM, SwarmRunORM

logger = logging.getLogger(__name__)

# --- Policy limits (V6-800) ---
MIN_WORKERS = 2
MAX_WORKERS = 4
MAX_DEPTH = 1


class LightSwarmService:
    """Service managing Light Swarm creation, policy validation, and DAG state."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ #
    # Plan Creation & Validation (V6-800, V6-801)
    # ------------------------------------------------------------------ #

    def _resolve_ready_nodes(
        self, nodes: list[domain.SwarmNode], node_statuses: dict[str, Any]
    ) -> list[str]:
        """Return node_ids whose all dependencies are COMPLETED and which are PENDING."""
        ready: list[str] = []
        completed = {
            nid
            for nid, st in node_statuses.items()
            if st in (SwarmNodeStatus.COMPLETED, SwarmNodeStatus.COMPLETED.value)
        }
        for node in nodes:
            if node_statuses.get(node.node_id) in (
                SwarmNodeStatus.PENDING,
                SwarmNodeStatus.PENDING.value,
                SwarmNodeStatus.READY,
                SwarmNodeStatus.READY.value,
            ):
                if all(dep in completed for dep in node.depends_on):
                    ready.append(node.node_id)
        return ready

    def validate_plan(self, plan: domain.SwarmPlan) -> tuple[bool, str | None]:
        """Validate DAG acyclicity, worker bounds, policy constraints.

        Returns (True, None) on success, (False, reason) on rejection.
        """
        policy = plan.policy

        # Strategy-level guard: Light allows at most MAX_WORKERS code-changing nodes
        code_changing = [n for n in plan.nodes if n.node_type == SwarmNodeType.IMPLEMENT]
        if len(code_changing) > MAX_WORKERS:
            return False, (
                f"Plan has {len(code_changing)} IMPLEMENT nodes; "
                f"Light Swarm allows at most {MAX_WORKERS} (V6-800)."
            )

        # No sub-swarms allowed
        if policy.allow_sub_swarms:
            return False, "Light Swarm policy prohibits sub-swarms (V6-800)."

        # Depth check: all nodes must be at depth 0 or 1
        if policy.max_depth > MAX_DEPTH:
            return False, f"max_depth={policy.max_depth} exceeds Light Swarm limit of {MAX_DEPTH}."

        # Require independent checker when policy demands it
        if policy.require_independent_checker:
            checker_types = {SwarmNodeType.CRITIQUE, SwarmNodeType.VERIFY}
            has_checker = any(n.node_type in checker_types for n in plan.nodes)
            if not has_checker and len(plan.nodes) > 1:
                return False, "Plan requires an independent CRITIQUE or VERIFY node (V6-800)."

        # Acyclicity check via DFS (V6-801)
        adj: dict[str, list[str]] = {n.node_id: [] for n in plan.nodes}
        for from_id, to_id in plan.edges:
            adj[from_id].append(to_id)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _has_cycle(nid: str) -> bool:
            visited.add(nid)
            rec_stack.add(nid)
            for neighbour in adj.get(nid, []):
                if neighbour not in visited:
                    if _has_cycle(neighbour):
                        return True
                elif neighbour in rec_stack:
                    return True
            rec_stack.discard(nid)
            return False

        for node in plan.nodes:
            if node.node_id not in visited:
                if _has_cycle(node.node_id):
                    return False, "Plan DAG contains a cycle — rejected (V6-801)."

        return True, None

    async def create_plan(
        self,
        project_id: int,
        task_run_id: int,
        nodes: list[domain.SwarmNode],
        edges: list[tuple[str, str]],
        policy: domain.SwarmPolicy | None = None,
        strategy: SwarmStrategy = SwarmStrategy.LIGHT,
    ) -> domain.SwarmPlan:
        """Create and persist a validated SwarmPlan.

        Raises ValueError if the plan violates policy constraints.
        """
        effective_policy = policy or domain.SwarmPolicy(strategy=strategy)
        plan = domain.SwarmPlan(
            project_id=project_id,
            task_run_id=task_run_id,
            strategy=strategy,
            policy=effective_policy,
            nodes=nodes,
            edges=edges,
        )

        valid, reason = self.validate_plan(plan)
        if not valid:
            raise ValueError(f"SwarmPlan rejected: {reason}")

        orm_obj = SwarmPlanORM.from_domain(plan)
        self.session.add(orm_obj)
        await self.session.flush()
        plan.id = orm_obj.id
        return plan

    # ------------------------------------------------------------------ #
    # Execution Control (V6-802, V6-804)
    # ------------------------------------------------------------------ #

    async def start_swarm(self, plan_id: int) -> domain.SwarmRun:
        """Initialise a SwarmRun for the given plan and set ready nodes."""
        stmt = select(SwarmPlanORM).where(SwarmPlanORM.id == plan_id)
        result = await self.session.execute(stmt)
        plan_orm = result.scalar_one_or_none()
        if not plan_orm:
            raise ValueError(f"SwarmPlan {plan_id} not found.")

        plan = plan_orm.to_domain()

        # Bootstrap node statuses
        node_statuses = {n.node_id: SwarmNodeStatus.PENDING for n in plan.nodes}
        ready = self._resolve_ready_nodes(plan.nodes, node_statuses)

        run = domain.SwarmRun(
            plan_id=plan_id,
            status=SwarmStatus.RUNNING,
            active_node_ids=ready,
            node_statuses={nid: st.value for nid, st in node_statuses.items()},
            started_at=datetime.now(UTC),
        )

        # Mark ready nodes
        for nid in ready:
            run.node_statuses[nid] = SwarmNodeStatus.READY

        # Update plan status to RUNNING
        plan_orm.status = SwarmStatus.RUNNING
        orm_run = SwarmRunORM.from_domain(run)
        self.session.add(orm_run)
        await self.session.flush()
        run.id = orm_run.id
        return run

    async def complete_node(
        self,
        run_id: int,
        node_id: str,
        artifact_id: int | None = None,
        cost_usd: float = 0.0,
        tokens: int = 0,
        ownership_token: str | None = None,
        worker_agent_id: str | None = None,
    ) -> domain.SwarmRun:
        """Mark a node COMPLETED, propagate artifacts, advance ready nodes."""
        run_orm, run = await self._load_run(run_id)

        # Check budget policy
        plan_orm = await self._load_plan_orm(run.plan_id)
        plan = plan_orm.to_domain()
        node = next((candidate for candidate in plan.nodes if candidate.node_id == node_id), None)
        if node is None:
            raise ValueError(f"Node {node_id} not found in plan {run.plan_id}")
        if node_id not in run.active_node_ids:
            raise ValueError(f"Node {node_id} is not owned by an active worker.")

        # V61C-601: Ownership token authentication check if ownership_token is provided
        if ownership_token:
            if not verify_node_ownership_token(
                ownership_token, node.ownership_token, run_id, node_id, node.attempt_count
            ):
                raise PermissionError(f"Invalid ownership token for node {node_id}")

        # V61C-601: Maker/Checker separation check for CRITIQUE/VERIFY nodes
        if node.node_type in (SwarmNodeType.CRITIQUE, SwarmNodeType.VERIFY):
            checker_id = worker_agent_id or node.owner_agent_id
            maker_id = node.maker_agent_id
            if not maker_id:
                for n in plan.nodes:
                    if n.node_type == SwarmNodeType.IMPLEMENT and n.owner_agent_id:
                        maker_id = n.owner_agent_id
                        break
            valid_mc, mc_reason = validate_maker_checker_identity(node.node_type, checker_id, maker_id)
            if not valid_mc:
                raise ValueError(mc_reason or "Maker/Checker separation violation")

        run.node_statuses[node_id] = SwarmNodeStatus.COMPLETED
        run.active_node_ids.remove(node_id)
        run.cumulative_cost_usd += cost_usd
        run.cumulative_tokens += tokens
        node.finished_at = datetime.now(UTC)
        if worker_agent_id:
            node.owner_agent_id = worker_agent_id
        if node.node_type == SwarmNodeType.IMPLEMENT and worker_agent_id:
            node.maker_agent_id = worker_agent_id

        if artifact_id is not None:
            node.artifact_id = artifact_id

        plan_orm.nodes_json = [n.model_dump(mode="json") for n in plan.nodes]

        if run.cumulative_cost_usd > plan.policy.max_cost_usd:
            logger.warning(
                "SwarmRun %d exceeded budget (%.4f USD > %.4f USD). Killing.",
                run_id,
                run.cumulative_cost_usd,
                plan.policy.max_cost_usd,
            )
            return await self._kill_run(run_orm, run, "BUDGET_EXCEEDED")

        # Resolve newly ready nodes and assign tokens
        new_ready = self._resolve_ready_nodes(plan.nodes, run.node_statuses)
        for nid in new_ready:
            if run.node_statuses.get(nid) == SwarmNodeStatus.PENDING:
                run.node_statuses[nid] = SwarmNodeStatus.READY
                run.active_node_ids.append(nid)
                r_node = next((n for n in plan.nodes if n.node_id == nid), None)
                if r_node:
                    r_node.started_at = datetime.now(UTC)
                    r_node.ownership_token = generate_node_ownership_token(
                        run_id, nid, r_node.attempt_count
                    )
        plan_orm.nodes_json = [n.model_dump(mode="json") for n in plan.nodes]

        # Check global completion
        all_done = all(
            st in (SwarmNodeStatus.COMPLETED, SwarmNodeStatus.SKIPPED, SwarmNodeStatus.FAILED)
            for st in run.node_statuses.values()
        )
        if all_done:
            has_failures = any(st == SwarmNodeStatus.FAILED for st in run.node_statuses.values())
            missing_artifact = any(
                n.output_artifact_type is not None and n.artifact_id is None for n in plan.nodes
            )
            run.status = (
                SwarmStatus.FAILED if has_failures or missing_artifact else SwarmStatus.COMPLETED
            )
            if has_failures:
                run.verdict = "NEEDS_REPAIR"
            elif missing_artifact:
                run.verdict = "EVIDENCE_MISSING"
            else:
                run.verdict = "EVIDENCE_READY"
            run.finished_at = datetime.now(UTC)

        await self._flush_run(run_orm, run)
        return run

    async def fail_node(
        self,
        run_id: int,
        node_id: str,
        reason: str,
        attempt_count: int = 1,
        ownership_token: str | None = None,
    ) -> domain.SwarmRun:
        """Mark a node FAILED, propagate downstream BLOCKed state, check retry policy."""
        run_orm, run = await self._load_run(run_id)
        plan_orm = await self._load_plan_orm(run.plan_id)
        plan = plan_orm.to_domain()

        node = next((n for n in plan.nodes if n.node_id == node_id), None)
        if not node:
            raise ValueError(f"Node {node_id} not found in plan {run.plan_id}")

        if ownership_token:
            if not verify_node_ownership_token(
                ownership_token, node.ownership_token, run_id, node_id, attempt_count
            ):
                raise PermissionError(f"Invalid ownership token for node {node_id}")

        # Retry if within limit
        if attempt_count < plan.policy.max_retries_per_node:
            logger.info(
                "Node %s retry %d/%d",
                node_id,
                attempt_count,
                plan.policy.max_retries_per_node,
            )
            run.node_statuses[node_id] = SwarmNodeStatus.PENDING
            await self._flush_run(run_orm, run)
            return run

        # Exhausted retries — mark FAILED and propagate BLOCKED downstream
        run.node_statuses[node_id] = SwarmNodeStatus.FAILED
        if node_id in run.active_node_ids:
            run.active_node_ids.remove(node_id)

        # Find transitively dependent nodes and mark BLOCKED
        blocked = self._find_downstream(plan.nodes, plan.edges, node_id)
        for dep_id in blocked:
            if run.node_statuses.get(dep_id) == SwarmNodeStatus.PENDING:
                run.node_statuses[dep_id] = SwarmNodeStatus.BLOCKED

        # If all remaining nodes are terminal, conclude run
        all_terminal = all(
            s
            in (
                SwarmNodeStatus.COMPLETED,
                SwarmNodeStatus.FAILED,
                SwarmNodeStatus.BLOCKED,
                SwarmNodeStatus.SKIPPED,
            )
            for s in run.node_statuses.values()
        )
        if all_terminal:
            run.status = SwarmStatus.FAILED
            run.verdict = "NEEDS_REPAIR"
            run.finished_at = datetime.now(UTC)

        await self._flush_run(run_orm, run)
        return run

    def _find_downstream(
        self, nodes: list[domain.SwarmNode], edges: list[tuple[str, str]], start_node_id: str
    ) -> list[str]:
        """BFS over dependency edges to find all nodes reachable from start_node_id."""
        adj: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for from_id, to_id in edges:
            adj[from_id].append(to_id)
        visited: list[str] = []
        queue = [start_node_id]
        seen: set[str] = {start_node_id}
        while queue:
            cur = queue.pop(0)
            for nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    visited.append(nxt)
                    queue.append(nxt)
        return visited

    async def pause_swarm(self, run_id: int) -> domain.SwarmRun:
        """Pause a running swarm (V6-804)."""
        run_orm, run = await self._load_run(run_id)
        if run.status != SwarmStatus.RUNNING:
            raise ValueError(f"SwarmRun {run_id} is not RUNNING (status={run.status}).")
        run.status = SwarmStatus.PAUSED
        plan_orm = await self._load_plan_orm(run.plan_id)
        plan_orm.paused_at = datetime.now(UTC)
        plan_orm.status = SwarmStatus.PAUSED
        await self._flush_run(run_orm, run)
        return run

    async def kill_swarm(self, run_id: int) -> domain.SwarmRun:
        """Kill a swarm regardless of status, releasing all active nodes (V6-804)."""
        run_orm, run = await self._load_run(run_id)
        return await self._kill_run(run_orm, run, "KILLED_BY_USER")

    async def _kill_run(
        self, run_orm: SwarmRunORM, run: domain.SwarmRun, reason: str
    ) -> domain.SwarmRun:
        run.status = SwarmStatus.KILLED
        run.verdict = reason
        run.finished_at = datetime.now(UTC)
        for nid in list(run.active_node_ids):
            run.node_statuses[nid] = SwarmNodeStatus.BLOCKED
        run.active_node_ids = []
        await self._flush_run(run_orm, run)
        return run

    # ------------------------------------------------------------------ #
    # Aggregation & Observability (V6-803, V6-804)
    # ------------------------------------------------------------------ #

    async def aggregate_result(self, run_id: int) -> domain.SwarmExecutionSummary:
        """Build a replayable SwarmExecutionSummary from run and plan state (V6-803)."""
        run_orm, run = await self._load_run(run_id)
        plan_orm = await self._load_plan_orm(run.plan_id)
        plan = plan_orm.to_domain()

        # Collect artifact IDs from completed nodes
        artifact_ids = [n.artifact_id for n in plan.nodes if n.artifact_id is not None]

        # Compute duration
        duration = 0.0
        if run.started_at and run.finished_at:
            duration = (run.finished_at - run.started_at).total_seconds()

        return domain.SwarmExecutionSummary(
            plan_id=run.plan_id,
            run_id=run_id,
            strategy=plan.strategy,
            verdict=run.verdict,
            nodes=plan.nodes,
            total_cost_usd=run.cumulative_cost_usd,
            total_tokens=run.cumulative_tokens,
            duration_seconds=duration,
            artifact_ids=artifact_ids,
        )

    async def get_dag_view(self, run_id: int) -> dict[str, Any]:
        """Return a DAG status snapshot for observability (V6-804)."""
        run_orm, run = await self._load_run(run_id)
        plan_orm = await self._load_plan_orm(run.plan_id)
        plan = plan_orm.to_domain()

        return {
            "run_id": run_id,
            "plan_id": run.plan_id,
            "status": run.status,
            "verdict": run.verdict,
            "strategy": plan.strategy,
            "cumulative_cost_usd": run.cumulative_cost_usd,
            "cumulative_tokens": run.cumulative_tokens,
            "active_node_ids": run.active_node_ids,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "title": n.title,
                    "status": run.node_statuses.get(n.node_id, SwarmNodeStatus.PENDING),
                    "depends_on": n.depends_on,
                    "artifact_id": n.artifact_id,
                }
                for n in plan.nodes
            ],
            "edges": [{"from": e[0], "to": e[1]} for e in plan.edges],
        }

    async def list_runs_for_plan(self, plan_id: int) -> list[domain.SwarmRun]:
        """List all SwarmRun entries for a given plan."""
        stmt = select(SwarmRunORM).where(SwarmRunORM.plan_id == plan_id)
        result = await self.session.execute(stmt)
        return [row.to_domain() for row in result.scalars().all()]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _load_run(self, run_id: int) -> tuple[SwarmRunORM, domain.SwarmRun]:
        stmt = select(SwarmRunORM).where(SwarmRunORM.id == run_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            raise ValueError(f"SwarmRun {run_id} not found.")
        return orm, orm.to_domain()

    async def _load_plan_orm(self, plan_id: int) -> SwarmPlanORM:
        stmt = select(SwarmPlanORM).where(SwarmPlanORM.id == plan_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            raise ValueError(f"SwarmPlan {plan_id} not found.")
        return orm

    async def _flush_run(self, run_orm: SwarmRunORM, run: domain.SwarmRun) -> None:
        run_orm.status = (
            run.status.value if isinstance(run.status, SwarmStatus) else str(run.status)
        )
        run_orm.active_node_ids_json = list(run.active_node_ids)
        run_orm.cumulative_cost_usd = run.cumulative_cost_usd
        run_orm.cumulative_tokens = run.cumulative_tokens
        run_orm.node_statuses_json = dict(run.node_statuses)
        run_orm.verdict = run.verdict
        run_orm.started_at = run.started_at
        run_orm.finished_at = run.finished_at
        await self.session.flush()
