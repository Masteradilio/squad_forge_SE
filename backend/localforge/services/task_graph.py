"""Task Graph service — server-owned dynamic DAG with versioned mutations and Deep Swarm.

Implements V6-900 through V6-904:
- Versioned graph snapshots with SHA-256 content hashes (V6-900)
- Validated append-only mutation journal (V6-901):
  SPLIT_TASK, APPEND_CHILD, ADD_DEPENDENCY, ADD_CRITIQUE, ADD_VERIFIER,
  SUPERSEDE_NODE, CANCEL_SUBTREE
- Stale-version, ownership, acyclicity, depth, fan-out, and budget rejection (V6-901)
- Composite node completion from child evidence and explicit gates (V6-902)
- Deep Swarm policy enforcement — opt-in, experimental, disabled by default (V6-903)
- Crash recovery and graph reconciliation after restart (V6-904)
"""

import hashlib
import json
import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import (
    DeepSwarmStatus,
    GraphMutationType,
    GraphNodeKind,
    SwarmNodeStatus,
    SwarmNodeType,
    TypedArtifactType,
)
from localforge.storage.orm import (
    DeepSwarmRunORM,
    GraphMutationEntryORM,
    PathLeaseORM,
    SwarmPlanORM,
    TaskGraphVersionORM,
    TypedHandoffArtifactORM,
    WorktreeAttemptManifestORM,
)

logger = logging.getLogger(__name__)


def _compute_graph_hash(nodes_json: list[Any], edges_json: list[Any]) -> str:
    """SHA-256 hash of canonical serialized graph (nodes + edges)."""
    payload = {"nodes": nodes_json, "edges": edges_json}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _compute_mutation_hash(
    *,
    plan_id: int,
    mutation_sequence: int,
    graph_version: int,
    parent_graph_version: int,
    mutation_type: str,
    actor_agent_id: str,
    reason: str,
    payload: dict[str, Any],
) -> str:
    """SHA-256 hash of the complete immutable mutation identity."""
    data = {
        "plan_id": plan_id,
        "mutation_sequence": mutation_sequence,
        "graph_version": graph_version,
        "parent_graph_version": parent_graph_version,
        "mutation_type": mutation_type,
        "actor_agent_id": actor_agent_id,
        "reason": reason,
        "payload": payload,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


class TaskGraphService:
    """Server-owned dynamic DAG with policy enforcement and crash recovery."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ #
    # V6-900: Versioned graph management
    # ------------------------------------------------------------------ #

    async def create_initial_graph_version(self, plan_id: int) -> domain.TaskGraphVersion:
        """Create the initial (version 0) graph snapshot from an existing SwarmPlan."""
        existing = await self.get_latest_graph_version(plan_id)
        if existing is not None:
            raise ValueError(f"Graph for plan {plan_id} is already initialized.")
        plan_orm = await self._load_plan_orm(plan_id)
        plan = plan_orm.to_domain()

        nodes_json = [n.model_dump(mode="json") for n in plan.nodes]
        edges_json = [list(e) for e in plan.edges]
        content_hash = _compute_graph_hash(nodes_json, edges_json)

        gv = domain.TaskGraphVersion(
            plan_id=plan_id,
            version=0,
            nodes_snapshot_json=nodes_json,
            edges_snapshot_json=edges_json,
            content_hash=content_hash,
            mutation_id=None,
        )
        orm_obj = TaskGraphVersionORM.from_domain(gv)
        self.session.add(orm_obj)
        await self.session.flush()
        gv.id = orm_obj.id
        return gv

    async def get_latest_graph_version(self, plan_id: int) -> domain.TaskGraphVersion | None:
        """Return the highest-version graph snapshot for a plan."""
        stmt = (
            select(TaskGraphVersionORM)
            .where(TaskGraphVersionORM.plan_id == plan_id)
            .order_by(TaskGraphVersionORM.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def replay_graph(self, plan_id: int) -> domain.TaskGraphVersion | None:
        """Replay mutation journal from version 0 to reconstruct current graph state (V6-900)."""
        initial_result = await self.session.execute(
            select(TaskGraphVersionORM).where(
                TaskGraphVersionORM.plan_id == plan_id,
                TaskGraphVersionORM.version == 0,
            )
        )
        initial = initial_result.scalar_one_or_none()
        if initial is None:
            return None

        nodes = deepcopy(initial.nodes_snapshot_json or [])
        edges = deepcopy(initial.edges_snapshot_json or [])
        if _compute_graph_hash(nodes, edges) != initial.content_hash:
            raise ValueError("Initial graph snapshot content hash mismatch.")

        journal = await self.get_mutation_journal(plan_id)
        expected_parent = 0
        for expected_sequence, mutation in enumerate(journal, start=1):
            if mutation.mutation_sequence != expected_sequence:
                raise ValueError("Mutation journal sequence is not contiguous.")
            if mutation.parent_graph_version != expected_parent:
                raise ValueError("Mutation journal parent version is not contiguous.")
            if mutation.graph_version != expected_parent + 1:
                raise ValueError("Mutation journal graph version is not contiguous.")
            expected_hash = _compute_mutation_hash(
                plan_id=plan_id,
                mutation_sequence=mutation.mutation_sequence,
                graph_version=mutation.graph_version,
                parent_graph_version=mutation.parent_graph_version,
                mutation_type=mutation.mutation_type.value,
                actor_agent_id=mutation.actor_agent_id,
                reason=mutation.reason,
                payload=mutation.payload_json,
            )
            if mutation.content_hash != expected_hash:
                raise ValueError(f"Mutation journal hash mismatch at sequence {expected_sequence}.")
            node_map = {node["node_id"]: node for node in nodes}
            self._apply_mutation_to_graph(
                mutation.mutation_type,
                deepcopy(mutation.payload_json),
                nodes,
                edges,
                node_map,
            )
            expected_parent = mutation.graph_version

        reconstructed_hash = _compute_graph_hash(nodes, edges)
        latest = await self.get_latest_graph_version(plan_id)
        if latest is None:
            return None
        if latest.version != expected_parent or latest.content_hash != reconstructed_hash:
            raise ValueError("Latest graph snapshot diverges from deterministic replay.")
        return domain.TaskGraphVersion(
            id=latest.id,
            plan_id=plan_id,
            version=expected_parent,
            nodes_snapshot_json=nodes,
            edges_snapshot_json=edges,
            content_hash=reconstructed_hash,
            mutation_id=latest.mutation_id,
            created_at=latest.created_at,
        )

    async def get_mutation_journal(self, plan_id: int) -> list[domain.GraphMutationEntry]:
        """Return full append-only mutation journal for a plan."""
        stmt = (
            select(GraphMutationEntryORM)
            .where(GraphMutationEntryORM.plan_id == plan_id)
            .order_by(GraphMutationEntryORM.graph_version.asc())
        )
        result = await self.session.execute(stmt)
        return [row.to_domain() for row in result.scalars().all()]

    # ------------------------------------------------------------------ #
    # V6-901: Validated graph mutations
    # ------------------------------------------------------------------ #

    async def apply_mutation(
        self,
        plan_id: int,
        mutation_type: GraphMutationType,
        actor_agent_id: str,
        reason: str,
        payload: dict[str, Any],
        expected_graph_version: int,
        deep_swarm_run_id: int | None = None,
    ) -> tuple[domain.GraphMutationEntry, domain.TaskGraphVersion]:
        """Apply a validated mutation to the graph.

        Validates:
        - Stale version guard (V6-901): rejects if current version != expected
        - Ownership: actor must own the affected node when required
        - Acyclicity: new dependencies must not create cycles
        - Deep Swarm limits: max_depth, max_nodes, max_mutations

        Returns (mutation_entry, new_graph_version).
        Raises ValueError on any constraint violation.
        """
        actor_agent_id = actor_agent_id.strip()
        reason = reason.strip()
        if not actor_agent_id:
            raise ValueError("Mutation actor_agent_id is required.")
        if not reason:
            raise ValueError("Dynamic expansion requires a non-empty justification.")
        if deep_swarm_run_id is None and not actor_agent_id.startswith("server:"):
            raise ValueError("Agent-proposed mutations require an enabled Deep Swarm run.")

        current_gv = await self.get_latest_graph_version(plan_id)
        if current_gv is None:
            raise ValueError(
                f"No graph version found for plan {plan_id}. Create initial version first."
            )

        # Stale-version rejection (V6-901)
        if current_gv.version != expected_graph_version:
            raise ValueError(
                f"Stale mutation rejected: expected graph_version={expected_graph_version}, "
                f"current={current_gv.version}. Reload and retry."
            )

        policy = domain.DeepSwarmPolicy()
        run_orm: DeepSwarmRunORM | None = None
        run: domain.DeepSwarmRun | None = None
        if deep_swarm_run_id is not None:
            run_orm, run = await self._load_deep_run(deep_swarm_run_id)
            if run.plan_id != plan_id:
                raise ValueError("Deep Swarm run does not own the requested graph.")
            if run.status not in (
                DeepSwarmStatus.RUNNING,
                DeepSwarmStatus.EXPANDING,
            ):
                raise ValueError("Deep Swarm run is not enabled for graph expansion.")
            policy = run.policy
            if run.mutation_count >= policy.max_mutations:
                raise ValueError("Deep Swarm mutation budget exhausted.")
            if run.cumulative_paid_calls >= policy.max_paid_calls:
                raise ValueError("Deep Swarm paid-call budget exhausted.")
            if run.cumulative_cost_usd >= policy.max_cost_usd:
                raise ValueError("Deep Swarm cost budget exhausted.")
            if len(run.active_node_ids) > policy.max_concurrent_workers:
                raise ValueError("Deep Swarm worker capacity is unavailable.")
            decision_contract_id = str(payload.get("decision_contract_id", "")).strip()
            if not decision_contract_id:
                raise ValueError(
                    "Deep Swarm graph mutation requires payload.decision_contract_id."
                )
            if decision_contract_id not in policy.registered_decision_contract_ids:
                raise ValueError(
                    "Deep Swarm graph mutation decision_contract_id is not registered."
                )

        nodes = deepcopy(current_gv.nodes_snapshot_json)
        edges = deepcopy(current_gv.edges_snapshot_json)
        node_map = {n["node_id"]: n for n in nodes}

        self._validate_mutation_request(
            mutation_type,
            payload,
            actor_agent_id,
            nodes,
            edges,
            node_map,
            policy,
        )
        self._apply_mutation_to_graph(mutation_type, payload, nodes, edges, node_map)

        # Acyclicity check after mutation (V6-901)
        if not self._is_acyclic(nodes, edges):
            raise ValueError(f"Mutation {mutation_type} would create a cycle — rejected (V6-901).")

        self._validate_graph_bounds(nodes, edges, policy)

        new_version = current_gv.version + 1
        mutation_sequence = len(await self.get_mutation_journal(plan_id)) + 1
        content_hash_mutation = _compute_mutation_hash(
            plan_id=plan_id,
            mutation_sequence=mutation_sequence,
            graph_version=new_version,
            parent_graph_version=current_gv.version,
            mutation_type=mutation_type.value,
            actor_agent_id=actor_agent_id,
            reason=reason,
            payload=payload,
        )
        new_graph_hash = _compute_graph_hash(nodes, edges)

        # Persist mutation journal entry
        mutation = domain.GraphMutationEntry(
            plan_id=plan_id,
            mutation_sequence=mutation_sequence,
            graph_version=new_version,
            parent_graph_version=current_gv.version,
            mutation_type=mutation_type,
            actor_agent_id=actor_agent_id,
            reason=reason,
            payload_json=payload,
            content_hash=content_hash_mutation,
        )
        mut_orm = GraphMutationEntryORM.from_domain(mutation)
        self.session.add(mut_orm)
        await self.session.flush()
        mutation.id = mut_orm.id

        # Persist new graph version snapshot
        new_gv = domain.TaskGraphVersion(
            plan_id=plan_id,
            version=new_version,
            nodes_snapshot_json=nodes,
            edges_snapshot_json=edges,
            content_hash=new_graph_hash,
            mutation_id=mutation.id,
        )
        gv_orm = TaskGraphVersionORM.from_domain(new_gv)
        self.session.add(gv_orm)
        await self.session.flush()
        new_gv.id = gv_orm.id

        if run_orm is not None and run is not None:
            run.mutation_count += 1
            run.current_graph_version = new_version
            for node in nodes:
                run.node_statuses.setdefault(node["node_id"], SwarmNodeStatus.PENDING.value)
            run.active_node_ids = self._resolve_ready_node_ids(
                nodes,
                edges,
                run.node_statuses,
            )[: run.policy.max_concurrent_workers]
            run.status = DeepSwarmStatus.EXPANDING
            await self._flush_deep_run(run_orm, run)

        logger.info(
            "Graph mutation applied: plan=%d version=%d->%d type=%s actor=%s",
            plan_id,
            current_gv.version,
            new_version,
            mutation_type.value,
            actor_agent_id,
        )
        return mutation, new_gv

    def _validate_mutation_request(
        self,
        mutation_type: GraphMutationType,
        payload: dict[str, Any],
        actor_agent_id: str,
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
        node_map: dict[str, dict[str, Any]],
        policy: domain.DeepSwarmPolicy,
    ) -> None:
        """Validate ownership, payload safety, artifacts, and node references."""
        forbidden_agent_fields = {
            "status",
            "depends_on",
            "runner_id",
            "worktree_path",
            "artifact_id",
            "attempt_count",
            "side_effect_completed",
        }

        def _walk(value: Any) -> None:
            if isinstance(value, dict):
                forbidden = forbidden_agent_fields.intersection(value)
                if forbidden:
                    names = ", ".join(sorted(forbidden))
                    raise ValueError(f"Agent mutation cannot set server-owned fields: {names}.")
                for nested in value.values():
                    _walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    _walk(nested)

        _walk(payload)

        affected_key = {
            GraphMutationType.APPEND_CHILD: "parent_node_id",
            GraphMutationType.ADD_DEPENDENCY: "to_node_id",
            GraphMutationType.ADD_CRITIQUE: "target_node_id",
            GraphMutationType.ADD_VERIFIER: "target_node_id",
            GraphMutationType.SUPERSEDE_NODE: "old_node_id",
            GraphMutationType.CANCEL_SUBTREE: "root_node_id",
            GraphMutationType.SPLIT_TASK: "original_node_id",
        }[mutation_type]
        affected_id = payload.get(affected_key)
        if not isinstance(affected_id, str) or affected_id not in node_map:
            raise ValueError(f"Mutation target {affected_key} must reference an existing node.")
        owner = node_map[affected_id].get("owner_agent_id")
        if owner and owner != actor_agent_id and not actor_agent_id.startswith("server:"):
            raise ValueError(f"Ownership rejected: node {affected_id} belongs to {owner}.")

        if mutation_type == GraphMutationType.ADD_DEPENDENCY:
            source_id = payload.get("from_node_id")
            if not isinstance(source_id, str) or source_id not in node_map:
                raise ValueError("from_node_id must reference an existing node.")

        new_nodes: list[dict[str, Any]] = []
        if mutation_type == GraphMutationType.SPLIT_TASK:
            raw_children = payload.get("child_node_ids")
            if not isinstance(raw_children, list) or not raw_children:
                raise ValueError("SPLIT_TASK requires at least one child node.")
            if len(raw_children) > policy.max_fan_out:
                raise ValueError("SPLIT_TASK exceeds the Deep Swarm fan-out limit.")
            new_nodes = raw_children
        elif mutation_type == GraphMutationType.APPEND_CHILD:
            new_nodes = [payload]
        elif mutation_type in (
            GraphMutationType.ADD_CRITIQUE,
            GraphMutationType.ADD_VERIFIER,
        ):
            default_prefix = (
                "critique" if mutation_type == GraphMutationType.ADD_CRITIQUE else "verify"
            )
            new_nodes = [
                {
                    **payload,
                    "node_id": payload.get("node_id", f"{default_prefix}-{affected_id}"),
                }
            ]
        elif mutation_type == GraphMutationType.SUPERSEDE_NODE:
            new_nodes = [
                {
                    **payload,
                    "node_id": payload.get("new_node_id"),
                    "node_type": payload.get("new_node_type", "IMPLEMENT"),
                }
            ]

        valid_node_types = {
            *(kind.value for kind in SwarmNodeType),
            *(kind.value for kind in GraphNodeKind),
        }
        seen_ids = set(node_map)
        for new_node in new_nodes:
            node_id = new_node.get("node_id")
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValueError("Every new graph node requires a non-empty node_id.")
            if node_id in seen_ids:
                raise ValueError(f"Duplicate graph node_id rejected: {node_id}.")
            seen_ids.add(node_id)
            node_type = new_node.get("node_type", "IMPLEMENT")
            if str(node_type) not in valid_node_types:
                raise ValueError(f"Unsupported graph node_type: {node_type}.")
            for artifact_field in (
                "required_input_artifact_type",
                "output_artifact_type",
            ):
                artifact_type = new_node.get(artifact_field)
                if artifact_type is not None:
                    try:
                        TypedArtifactType(str(artifact_type))
                    except ValueError as exc:
                        raise ValueError(
                            f"Invalid typed artifact contract: {artifact_type}."
                        ) from exc

        if "condition" in payload:
            contract_id = payload.get("decision_contract_id")
            if contract_id not in policy.registered_decision_contract_ids:
                raise ValueError("Conditional branches require a registered decision contract.")

        if len(edges) != len({tuple(edge) for edge in edges}):
            raise ValueError("Canonical graph already contains duplicate dependencies.")

    def _validate_graph_bounds(
        self,
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
        policy: domain.DeepSwarmPolicy,
    ) -> None:
        """Enforce node, depth, and fan-out bounds after a proposed mutation."""
        if len(nodes) > policy.max_nodes:
            raise ValueError("Mutation exceeds the Deep Swarm node budget.")
        if len(edges) != len({tuple(edge) for edge in edges}):
            raise ValueError("Graph contains duplicate dependencies.")

        node_ids = {node["node_id"] for node in nodes}
        if len(node_ids) != len(nodes):
            raise ValueError("Graph contains duplicate node IDs.")
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        indegree = {node_id: 0 for node_id in node_ids}
        for source, target in edges:
            if source not in node_ids or target not in node_ids:
                raise ValueError("Graph dependency references an unknown node.")
            adjacency[source].append(target)
            indegree[target] += 1
        if any(len(children) > policy.max_fan_out for children in adjacency.values()):
            raise ValueError("Mutation exceeds the Deep Swarm fan-out limit.")

        roots = [node_id for node_id, degree in indegree.items() if degree == 0]
        depths = {root: 0 for root in roots}
        queue = list(roots)
        while queue:
            source = queue.pop(0)
            for target in adjacency[source]:
                depths[target] = max(depths.get(target, 0), depths[source] + 1)
                queue.append(target)
        if depths and max(depths.values()) > policy.max_depth:
            raise ValueError("Mutation exceeds the Deep Swarm depth limit.")

    def _apply_mutation_to_graph(
        self,
        mutation_type: GraphMutationType,
        payload: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
        node_map: dict[str, dict[str, Any]],
    ) -> None:
        """Mutate nodes/edges in-place for the given mutation type (V6-901)."""
        if mutation_type == GraphMutationType.APPEND_CHILD:
            # payload: {node_id, node_type, title, description, parent_node_id}
            new_node: dict[str, Any] = {
                "node_id": payload["node_id"],
                "node_type": payload["node_type"],
                "title": payload.get("title", payload["node_id"]),
                "description": payload.get("description", ""),
                "status": SwarmNodeStatus.PENDING,
                "depends_on": [payload["parent_node_id"]] if payload.get("parent_node_id") else [],
                "attempt_count": 0,
            }
            nodes.append(new_node)
            if payload.get("parent_node_id"):
                edges.append([payload["parent_node_id"], payload["node_id"]])

        elif mutation_type == GraphMutationType.ADD_DEPENDENCY:
            # payload: {from_node_id, to_node_id}
            edges.append([payload["from_node_id"], payload["to_node_id"]])
            # Update depends_on in target node
            for n in nodes:
                if n["node_id"] == payload["to_node_id"]:
                    deps = n.get("depends_on", [])
                    if payload["from_node_id"] not in deps:
                        deps.append(payload["from_node_id"])
                    n["depends_on"] = deps

        elif mutation_type == GraphMutationType.ADD_CRITIQUE:
            # Append a CRITIQUE_GATE node depending on payload["target_node_id"]
            critique_id = payload.get("node_id", f"critique-{payload['target_node_id']}")
            nodes.append(
                {
                    "node_id": critique_id,
                    "node_type": GraphNodeKind.CRITIQUE_GATE,
                    "title": f"Critique: {payload['target_node_id']}",
                    "description": payload.get("description", "Independent critique gate"),
                    "status": SwarmNodeStatus.PENDING,
                    "depends_on": [payload["target_node_id"]],
                    "attempt_count": 0,
                }
            )
            edges.append([payload["target_node_id"], critique_id])

        elif mutation_type == GraphMutationType.ADD_VERIFIER:
            # Append a VERIFICATION_GATE node
            verifier_id = payload.get("node_id", f"verify-{payload['target_node_id']}")
            nodes.append(
                {
                    "node_id": verifier_id,
                    "node_type": GraphNodeKind.VERIFICATION_GATE,
                    "title": f"Verify: {payload['target_node_id']}",
                    "description": payload.get("description", "Verification gate"),
                    "status": SwarmNodeStatus.PENDING,
                    "depends_on": [payload["target_node_id"]],
                    "attempt_count": 0,
                }
            )
            edges.append([payload["target_node_id"], verifier_id])

        elif mutation_type == GraphMutationType.SUPERSEDE_NODE:
            # payload: {old_node_id, new_node_id, new_node_type, title, description}
            old_id = payload["old_node_id"]
            new_id = payload["new_node_id"]
            # Mark old as SKIPPED
            for n in nodes:
                if n["node_id"] == old_id:
                    n["status"] = SwarmNodeStatus.SKIPPED
            # Add new node inheriting old's dependencies
            old_deps = node_map.get(old_id, {}).get("depends_on", [])
            nodes.append(
                {
                    "node_id": new_id,
                    "node_type": payload.get("new_node_type", "IMPLEMENT"),
                    "title": payload.get("title", new_id),
                    "description": payload.get("description", ""),
                    "status": SwarmNodeStatus.PENDING,
                    "depends_on": old_deps,
                    "attempt_count": 0,
                }
            )
            # Redirect edges from old_id to new_id (outgoing)
            for e in edges:
                if e[0] == old_id:
                    e[0] = new_id

        elif mutation_type == GraphMutationType.CANCEL_SUBTREE:
            # payload: {root_node_id}
            to_cancel = self._bfs_descendants(payload["root_node_id"], nodes, edges)
            to_cancel.add(payload["root_node_id"])
            for n in nodes:
                if n["node_id"] in to_cancel:
                    n["status"] = SwarmNodeStatus.BLOCKED

        elif mutation_type == GraphMutationType.SPLIT_TASK:
            # child_node_ids contains the server-validated child specifications.
            parent_id = payload["original_node_id"]
            for child in payload.get("child_node_ids", []):
                nodes.append(
                    {
                        "node_id": child["node_id"],
                        "node_type": child.get("node_type", "IMPLEMENT"),
                        "title": child.get("title", child["node_id"]),
                        "description": child.get("description", ""),
                        "status": SwarmNodeStatus.PENDING,
                        "depends_on": [parent_id],
                        "attempt_count": 0,
                    }
                )
                edges.append([parent_id, child["node_id"]])

    def _bfs_descendants(
        self, start: str, nodes: list[dict[str, Any]], edges: list[list[str]]
    ) -> set[str]:
        """BFS to find all nodes reachable (downstream) from start."""
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e[0], []).append(e[1])
        visited: set[str] = set()
        queue = [start]
        while queue:
            cur = queue.pop(0)
            for nxt in adj.get(cur, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return visited

    def _is_acyclic(self, nodes: list[dict[str, Any]], edges: list[list[str]]) -> bool:
        """DFS cycle detection — return True if acyclic."""
        adj: dict[str, list[str]] = {n["node_id"]: [] for n in nodes}
        for e in edges:
            adj.setdefault(e[0], []).append(e[1])
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _dfs(nid: str) -> bool:
            visited.add(nid)
            rec_stack.add(nid)
            for nb in adj.get(nid, []):
                if nb not in visited:
                    if _dfs(nb):
                        return True
                elif nb in rec_stack:
                    return True
            rec_stack.discard(nid)
            return False

        for n in nodes:
            if n["node_id"] not in visited:
                if _dfs(n["node_id"]):
                    return False
        return True

    # ------------------------------------------------------------------ #
    # V6-902: Composite nodes and gates
    # ------------------------------------------------------------------ #

    def evaluate_composite_completion(
        self,
        node_id: str,
        nodes: list[dict[str, Any]],
        node_statuses: dict[str, str],
    ) -> bool:
        """Composite node is complete when all direct children are COMPLETED (V6-902)."""
        children = [n for n in nodes if node_id in n.get("depends_on", [])]
        if not children:
            return False
        return all(
            node_statuses.get(c["node_id"]) == SwarmNodeStatus.COMPLETED.value for c in children
        )

    def evaluate_composite_state(
        self,
        node_id: str,
        nodes: list[dict[str, Any]],
        node_statuses: dict[str, str],
    ) -> tuple[str, list[str]]:
        """Return deterministic composite state and preserved partial results."""
        children = [n for n in nodes if node_id in n.get("depends_on", [])]
        completed = [
            child["node_id"]
            for child in children
            if node_statuses.get(child["node_id"]) == SwarmNodeStatus.COMPLETED.value
        ]
        if not children:
            return SwarmNodeStatus.BLOCKED.value, []
        if len(completed) == len(children):
            return SwarmNodeStatus.COMPLETED.value, completed
        if any(
            node_statuses.get(child["node_id"])
            in (SwarmNodeStatus.FAILED.value, SwarmNodeStatus.BLOCKED.value)
            for child in children
        ):
            return SwarmNodeStatus.BLOCKED.value, completed
        return SwarmNodeStatus.PENDING.value, completed

    def propagate_failure(
        self,
        failed_node_id: str,
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
        node_statuses: dict[str, str],
    ) -> dict[str, str]:
        """Block downstream nodes while preserving completed partial results."""
        updated = dict(node_statuses)
        updated[failed_node_id] = SwarmNodeStatus.FAILED.value
        for node_id in self._bfs_descendants(failed_node_id, nodes, edges):
            if updated.get(node_id) != SwarmNodeStatus.COMPLETED.value:
                updated[node_id] = SwarmNodeStatus.BLOCKED.value
        return updated

    def check_gate_readiness(
        self,
        node: dict[str, Any],
        artifact_types_available: set[str],
    ) -> tuple[bool, str | None]:
        """Verify that a gate node (CRITIQUE_GATE / VERIFICATION_GATE) can proceed (V6-902)."""
        kind = node.get("node_type", "")
        if kind == GraphNodeKind.CRITIQUE_GATE:
            if "CRITIQUE" not in artifact_types_available:
                return False, "CRITIQUE_GATE requires a CRITIQUE artifact."
        elif kind == GraphNodeKind.VERIFICATION_GATE:
            if "VERIFICATION" not in artifact_types_available:
                return False, "VERIFICATION_GATE requires a VERIFICATION artifact."
        return True, None

    # ------------------------------------------------------------------ #
    # V6-903: Deep Swarm lifecycle
    # ------------------------------------------------------------------ #

    async def create_deep_swarm_run(
        self,
        plan_id: int,
        policy: domain.DeepSwarmPolicy | None = None,
    ) -> domain.DeepSwarmRun:
        """Create a Deep Swarm run — disabled by default (V6-903).

        Deep Swarm requires explicit opt-in: policy.enabled = True.
        """
        await self._load_plan_orm(plan_id)
        graph = await self.get_latest_graph_version(plan_id)
        if graph is None:
            raise ValueError("Initialize the server-owned task graph first.")

        effective_policy = policy or domain.DeepSwarmPolicy()
        self._validate_graph_bounds(
            graph.nodes_snapshot_json,
            graph.edges_snapshot_json,
            effective_policy,
        )
        node_statuses = {
            node["node_id"]: str(node.get("status", SwarmNodeStatus.PENDING.value))
            for node in graph.nodes_snapshot_json
        }
        ready = self._resolve_ready_node_ids(
            graph.nodes_snapshot_json,
            graph.edges_snapshot_json,
            node_statuses,
        )
        fallback_verdict: str | None = None
        if (
            effective_policy.enabled
            and effective_policy.prefer_light_swarm
            and self._fits_light_swarm(graph.nodes_snapshot_json, graph.edges_snapshot_json)
        ):
            fallback_verdict = "FALLBACK_LIGHT_SWARM"
        elif effective_policy.enabled and effective_policy.max_concurrent_workers == 1:
            fallback_verdict = "FALLBACK_SINGLE_WORKER"
        elif effective_policy.enabled and not effective_policy.registered_decision_contract_ids:
            fallback_verdict = "EVIDENCE_REQUIRED"

        run = domain.DeepSwarmRun(
            plan_id=plan_id,
            status=(
                DeepSwarmStatus.DISABLED
                if (
                    not effective_policy.enabled
                    or fallback_verdict in {"FALLBACK_LIGHT_SWARM", "EVIDENCE_REQUIRED"}
                )
                else DeepSwarmStatus.PENDING
            ),
            policy=effective_policy,
            current_graph_version=graph.version,
            node_statuses=node_statuses,
            active_node_ids=ready[: effective_policy.max_concurrent_workers],
            verdict=fallback_verdict,
        )
        orm_obj = DeepSwarmRunORM.from_domain(run)
        self.session.add(orm_obj)
        await self.session.flush()
        run.id = orm_obj.id
        return run

    async def enable_deep_swarm(self, run_id: int) -> domain.DeepSwarmRun:
        """Opt-in to Deep Swarm execution. Requires policy.enabled = True (V6-903)."""
        run_orm, run = await self._load_deep_run(run_id)
        if not run.policy.enabled:
            raise ValueError(
                "Deep Swarm is opt-in experimental. Set policy.enabled=True to activate."
            )
        if run.verdict == "FALLBACK_LIGHT_SWARM":
            raise ValueError("Plan fits Light Swarm; Deep Swarm was not enabled.")
        if run.verdict == "EVIDENCE_REQUIRED":
            raise ValueError("Deep Swarm requires registered decision-contract evidence.")
        if run.status != DeepSwarmStatus.PENDING:
            raise ValueError(f"Deep Swarm run cannot be enabled from {run.status}.")
        run.status = DeepSwarmStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await self._flush_deep_run(run_orm, run)
        return run

    async def tick_deep_swarm(
        self,
        run_id: int,
        completed_node_ids: list[str] | None = None,
        *,
        cost_usd: float = 0.0,
        tokens: int = 0,
        paid_calls: int = 0,
    ) -> domain.DeepSwarmRun:
        """Advance the deep swarm: detect stalls, check budget, update active nodes (V6-903)."""
        run_orm, run = await self._load_deep_run(run_id)

        if run.status not in (DeepSwarmStatus.RUNNING, DeepSwarmStatus.EXPANDING):
            return run

        progress_made = bool(completed_node_ids)
        run.cumulative_cost_usd += max(cost_usd, 0.0)
        run.cumulative_tokens += max(tokens, 0)
        run.cumulative_paid_calls += max(paid_calls, 0)
        if progress_made:
            run.stall_ticks = 0
            for nid in completed_node_ids or []:
                if nid not in run.node_statuses:
                    raise ValueError(f"Unknown Deep Swarm node: {nid}.")
                if run.node_statuses[nid] != SwarmNodeStatus.RUNNING.value:
                    raise ValueError(f"Node {nid} cannot complete from {run.node_statuses[nid]}.")
                run.node_statuses[nid] = SwarmNodeStatus.COMPLETED.value
                if nid in run.active_node_ids:
                    run.active_node_ids.remove(nid)
            graph = await self.replay_graph(run.plan_id)
            if graph is None:
                raise ValueError("Canonical graph is unavailable during execution.")
            newly_ready = self._resolve_ready_node_ids(
                graph.nodes_snapshot_json,
                graph.edges_snapshot_json,
                run.node_statuses,
            )
            running = [
                node_id
                for node_id, node_status in run.node_statuses.items()
                if node_status == SwarmNodeStatus.RUNNING.value
            ]
            capacity = max(run.policy.max_concurrent_workers - len(running), 0)
            run.active_node_ids = running + newly_ready[:capacity]
            run.status = DeepSwarmStatus.RUNNING
            if all(
                status
                in (
                    SwarmNodeStatus.COMPLETED.value,
                    SwarmNodeStatus.SKIPPED.value,
                )
                for status in run.node_statuses.values()
            ):
                run.status = DeepSwarmStatus.COMPLETED
                run.verdict = "EVIDENCE_READY"
                run.finished_at = datetime.now(UTC)
        else:
            run.stall_ticks += 1

        # Stall detection (V6-903)
        if run.stall_ticks >= run.policy.stall_tick_threshold:
            logger.warning(
                "DeepSwarmRun %d stalled (ticks=%d). Marking STALLED.", run_id, run.stall_ticks
            )
            run.status = DeepSwarmStatus.STALLED
            run.verdict = "STALLED_NO_PROGRESS"
            run.finished_at = datetime.now(UTC)

        # Budget checks
        if run.mutation_count >= run.policy.max_mutations:
            logger.warning(
                "DeepSwarmRun %d hit max_mutations=%d. Killing.", run_id, run.policy.max_mutations
            )
            run.status = DeepSwarmStatus.FAILED
            run.verdict = "MAX_MUTATIONS_EXCEEDED"
            run.finished_at = datetime.now(UTC)
        elif run.cumulative_paid_calls > run.policy.max_paid_calls:
            run.status = DeepSwarmStatus.FAILED
            run.verdict = "MAX_PAID_CALLS_EXCEEDED"
            run.finished_at = datetime.now(UTC)
        elif run.cumulative_cost_usd > run.policy.max_cost_usd:
            logger.warning("DeepSwarmRun %d exceeded budget. Killing.", run_id)
            run.status = DeepSwarmStatus.FAILED
            run.verdict = "BUDGET_EXCEEDED"
            run.finished_at = datetime.now(UTC)
        elif (
            run.started_at is not None
            and (
                datetime.now(UTC)
                - (
                    run.started_at
                    if run.started_at.tzinfo is not None
                    else run.started_at.replace(tzinfo=UTC)
                )
            ).total_seconds()
            > run.policy.max_duration_seconds
        ):
            run.status = DeepSwarmStatus.FAILED
            run.verdict = "MAX_DURATION_EXCEEDED"
            run.finished_at = datetime.now(UTC)
        elif len(run.active_node_ids) > run.policy.max_concurrent_workers:
            run.status = DeepSwarmStatus.FAILED
            run.verdict = "MAX_CONCURRENT_WORKERS_EXCEEDED"
            run.finished_at = datetime.now(UTC)

        await self._flush_deep_run(run_orm, run)
        return run

    async def kill_deep_swarm(self, run_id: int) -> domain.DeepSwarmRun:
        """Kill a Deep Swarm run (V6-904)."""
        run_orm, run = await self._load_deep_run(run_id)
        run.status = DeepSwarmStatus.KILLED
        run.verdict = "KILLED_BY_USER"
        run.finished_at = datetime.now(UTC)
        await self._flush_deep_run(run_orm, run)
        return run

    async def start_node(self, run_id: int, node_id: str) -> domain.DeepSwarmRun:
        """Move a server-selected ready node to RUNNING."""
        run_orm, run = await self._load_deep_run(run_id)
        if run.status not in (DeepSwarmStatus.RUNNING, DeepSwarmStatus.EXPANDING):
            raise ValueError("Deep Swarm run is not executing.")
        if node_id not in run.active_node_ids:
            raise ValueError("Node is not in the server-owned ready queue.")
        running_count = sum(
            status == SwarmNodeStatus.RUNNING.value for status in run.node_statuses.values()
        )
        if running_count >= run.policy.max_concurrent_workers:
            raise ValueError("Deep Swarm worker capacity is exhausted.")
        run.node_statuses[node_id] = SwarmNodeStatus.RUNNING.value
        await self._flush_deep_run(run_orm, run)
        return run

    async def claim_external_side_effect(
        self,
        run_id: int,
        node_id: str,
        idempotency_key: str,
    ) -> bool:
        """Register the stable key a worker must pass to an external system."""
        run_orm, run = await self._load_deep_run(run_id)
        key = idempotency_key.strip()
        if not key:
            raise ValueError("External side effects require an idempotency key.")
        if key in run.completed_side_effect_keys:
            return False
        existing = run.node_side_effect_keys.get(node_id)
        if existing is not None and existing != key:
            raise ValueError("Node already owns a different idempotency key.")
        run.node_side_effect_keys[node_id] = key
        await self._flush_deep_run(run_orm, run)
        return True

    async def complete_external_side_effect(
        self,
        run_id: int,
        node_id: str,
        idempotency_key: str,
    ) -> domain.DeepSwarmRun:
        """Persist side-effect completion before the node can be accepted."""
        run_orm, run = await self._load_deep_run(run_id)
        if run.node_side_effect_keys.get(node_id) != idempotency_key:
            raise ValueError("Idempotency key was not claimed by this node.")
        if idempotency_key not in run.completed_side_effect_keys:
            run.completed_side_effect_keys.append(idempotency_key)
        run.node_statuses[node_id] = SwarmNodeStatus.COMPLETED.value
        if node_id in run.active_node_ids:
            run.active_node_ids.remove(node_id)
        await self._flush_deep_run(run_orm, run)
        return run

    # ------------------------------------------------------------------ #
    # V6-904: Crash recovery and reconciliation
    # ------------------------------------------------------------------ #

    async def reconcile_after_restart(self, plan_id: int) -> dict[str, Any]:
        """Restore graph/run queues and report persisted attempts, leases, artifacts."""
        plan_orm = await self._load_plan_orm(plan_id)
        try:
            graph = await self.replay_graph(plan_id)
        except ValueError as exc:
            run_pair = await self._load_latest_deep_run_for_plan(plan_id)
            if run_pair is not None:
                run_orm, run = run_pair
                run.status = DeepSwarmStatus.FAILED
                run.verdict = "ESCALATED_GRAPH_RECONCILIATION"
                run.finished_at = datetime.now(UTC)
                await self._flush_deep_run(run_orm, run)
            return {
                "plan_id": plan_id,
                "status": "ESCALATED",
                "reason": str(exc),
                "reconciled_nodes": [],
            }
        if graph is None:
            return {"plan_id": plan_id, "reconciled_nodes": [], "status": "NO_GRAPH"}

        run_pair = await self._load_latest_deep_run_for_plan(plan_id)
        reconciled: list[str] = []
        ready: list[str] = []
        if run_pair is not None:
            run_orm, run = run_pair
            for node_id, node_status in list(run.node_statuses.items()):
                if node_status != SwarmNodeStatus.RUNNING.value:
                    continue
                key = run.node_side_effect_keys.get(node_id)
                if key and key in run.completed_side_effect_keys:
                    run.node_statuses[node_id] = SwarmNodeStatus.COMPLETED.value
                else:
                    # Workers must reuse the persisted key when retrying externally.
                    run.node_statuses[node_id] = SwarmNodeStatus.PENDING.value
                reconciled.append(node_id)
            ready = self._resolve_ready_node_ids(
                graph.nodes_snapshot_json,
                graph.edges_snapshot_json,
                run.node_statuses,
            )
            run.active_node_ids = ready[: run.policy.max_concurrent_workers]
            run.current_graph_version = graph.version
            if run.status in (DeepSwarmStatus.RUNNING, DeepSwarmStatus.EXPANDING):
                run.status = DeepSwarmStatus.RUNNING
            await self._flush_deep_run(run_orm, run)

        attempts_result = await self.session.execute(
            select(WorktreeAttemptManifestORM.id).where(
                WorktreeAttemptManifestORM.task_run_id == plan_orm.task_run_id,
                WorktreeAttemptManifestORM.status == "ACTIVE",
            )
        )
        leases_result = await self.session.execute(
            select(PathLeaseORM.id).where(
                PathLeaseORM.task_run_id == plan_orm.task_run_id,
                PathLeaseORM.release_reason.is_(None),
                PathLeaseORM.expires_at > datetime.now(UTC),
            )
        )
        artifacts_result = await self.session.execute(
            select(TypedHandoffArtifactORM.id).where(
                TypedHandoffArtifactORM.task_run_id == plan_orm.task_run_id
            )
        )
        restored_attempt_ids = list(attempts_result.scalars().all())
        restored_lease_ids = list(leases_result.scalars().all())
        restored_artifact_ids = list(artifacts_result.scalars().all())

        logger.info(
            "Reconciliation complete for plan %d: nodes=%s ready=%s",
            plan_id,
            reconciled,
            ready,
        )
        return {
            "plan_id": plan_id,
            "graph_version": graph.version,
            "reconciled_nodes": reconciled,
            "ready_node_ids": ready,
            "restored_attempt_ids": restored_attempt_ids,
            "restored_lease_ids": restored_lease_ids,
            "restored_artifact_ids": restored_artifact_ids,
            "status": "RECONCILED" if reconciled else "CLEAN",
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _fits_light_swarm(
        self,
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
    ) -> bool:
        """Return whether fixed bounded decomposition can use Light Swarm."""
        if len(nodes) > 4:
            return False
        policy = domain.DeepSwarmPolicy(max_depth=1, max_nodes=4)
        try:
            self._validate_graph_bounds(nodes, edges, policy)
        except ValueError:
            return False
        return not any(
            str(node.get("node_type")) == GraphNodeKind.COMPOSITE.value for node in nodes
        )

    def _resolve_ready_node_ids(
        self,
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
        node_statuses: dict[str, str],
    ) -> list[str]:
        """Rebuild the deterministic ready queue from canonical graph state."""
        dependencies: dict[str, set[str]] = {
            node["node_id"]: set(node.get("depends_on", [])) for node in nodes
        }
        for source, target in edges:
            dependencies.setdefault(target, set()).add(source)
        completed = {
            node_id
            for node_id, status in node_statuses.items()
            if status == SwarmNodeStatus.COMPLETED.value
        }
        ready = [
            node["node_id"]
            for node in nodes
            if node_statuses.get(node["node_id"], SwarmNodeStatus.PENDING.value)
            in (SwarmNodeStatus.PENDING.value, SwarmNodeStatus.READY.value)
            and dependencies.get(node["node_id"], set()).issubset(completed)
        ]
        return sorted(ready)

    async def _load_plan_orm(self, plan_id: int) -> SwarmPlanORM:
        stmt = select(SwarmPlanORM).where(SwarmPlanORM.id == plan_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            raise ValueError(f"SwarmPlan {plan_id} not found.")
        return orm

    async def _load_deep_run(self, run_id: int) -> tuple[DeepSwarmRunORM, domain.DeepSwarmRun]:
        stmt = select(DeepSwarmRunORM).where(DeepSwarmRunORM.id == run_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            raise ValueError(f"DeepSwarmRun {run_id} not found.")
        return orm, orm.to_domain()

    async def _load_latest_deep_run_for_plan(
        self, plan_id: int
    ) -> tuple[DeepSwarmRunORM, domain.DeepSwarmRun] | None:
        result = await self.session.execute(
            select(DeepSwarmRunORM)
            .where(DeepSwarmRunORM.plan_id == plan_id)
            .order_by(DeepSwarmRunORM.id.desc())
            .limit(1)
        )
        orm = result.scalar_one_or_none()
        return (orm, orm.to_domain()) if orm is not None else None

    async def _flush_deep_run(self, run_orm: DeepSwarmRunORM, run: domain.DeepSwarmRun) -> None:
        run_orm.status = (
            run.status.value if isinstance(run.status, DeepSwarmStatus) else str(run.status)
        )
        run_orm.current_graph_version = run.current_graph_version
        run_orm.mutation_count = run.mutation_count
        run_orm.stall_ticks = run.stall_ticks
        run_orm.cumulative_cost_usd = run.cumulative_cost_usd
        run_orm.cumulative_tokens = run.cumulative_tokens
        run_orm.cumulative_paid_calls = run.cumulative_paid_calls
        run_orm.node_statuses_json = dict(run.node_statuses)
        run_orm.active_node_ids_json = list(run.active_node_ids)
        run_orm.node_side_effect_keys_json = dict(run.node_side_effect_keys)
        run_orm.completed_side_effect_keys_json = list(run.completed_side_effect_keys)
        run_orm.verdict = run.verdict
        run_orm.started_at = run.started_at
        run_orm.finished_at = run.finished_at
        await self.session.flush()
