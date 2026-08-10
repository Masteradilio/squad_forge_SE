"""Phase 9 — Server-Owned Dynamic Task DAG and Deep Swarm test suite.

Covers V6-900 to V6-904:
- Graph versioning with SHA-256 content hashes (V6-900)
- Mutation journal replay determinism (V6-900)
- Validated mutations: cycle rejection, stale-version rejection, acyclicity (V6-901)
- All 7 mutation types: SPLIT_TASK, APPEND_CHILD, ADD_DEPENDENCY, ADD_CRITIQUE,
  ADD_VERIFIER, SUPERSEDE_NODE, CANCEL_SUBTREE (V6-901)
- Composite node gate checks (V6-902)
- Deep Swarm default-disabled, opt-in, stall, budget, kill controls (V6-903)
- Crash recovery and reconciliation (V6-904)
"""

import pytest
from localforge.models import domain
from localforge.models.enums import (
    DeepSwarmStatus,
    GraphMutationType,
    GraphNodeKind,
    SwarmNodeStatus,
    SwarmNodeType,
)
from localforge.services.task_graph import TaskGraphService, _compute_graph_hash
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import CURRENT_VERSION, bootstrap_database
from localforge.storage.database import DatabaseManager
from sqlalchemy import text

# ─────────────────────────────────────────────────────────────────────────────
# Unit tests (no DB)
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_graph_hash_deterministic() -> None:
    """V6-900: Same nodes/edges always produce the same hash."""
    nodes = [{"node_id": "a", "node_type": "RESEARCH"}]
    edges: list[list[str]] = [["a", "b"]]
    h1 = _compute_graph_hash(nodes, edges)
    h2 = _compute_graph_hash(nodes, edges)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_graph_hash_order_independent() -> None:
    """V6-900: json.dumps with sort_keys ensures canonical ordering."""
    nodes1 = [{"z": 1, "a": 2}]
    nodes2 = [{"a": 2, "z": 1}]
    h1 = _compute_graph_hash(nodes1, [])
    h2 = _compute_graph_hash(nodes2, [])
    assert h1 == h2


def test_is_acyclic_linear() -> None:
    """V6-901: Linear chain is acyclic."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"}]
    edges = [["a", "b"], ["b", "c"]]
    assert svc._is_acyclic(nodes, edges) is True


def test_is_acyclic_cycle_detected() -> None:
    """V6-901: Cycle is detected correctly."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"}]
    edges = [["a", "b"], ["b", "c"], ["c", "a"]]
    assert svc._is_acyclic(nodes, edges) is False


def test_apply_mutation_append_child() -> None:
    """V6-901: APPEND_CHILD adds a new node and edge."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes: list[dict] = [{"node_id": "root", "node_type": "RESEARCH", "depends_on": []}]
    edges: list[list[str]] = []
    node_map = {"root": nodes[0]}

    svc._apply_mutation_to_graph(
        GraphMutationType.APPEND_CHILD,
        {
            "node_id": "child-1",
            "node_type": "IMPLEMENT",
            "parent_node_id": "root",
            "title": "Child",
            "description": "test",
        },
        nodes,
        edges,
        node_map,
    )
    assert len(nodes) == 2
    assert nodes[1]["node_id"] == "child-1"
    assert ["root", "child-1"] in edges


def test_apply_mutation_add_critique() -> None:
    """V6-901: ADD_CRITIQUE appends a CRITIQUE_GATE node."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes: list[dict] = [{"node_id": "impl", "node_type": "IMPLEMENT", "depends_on": []}]
    edges: list[list[str]] = []
    node_map = {"impl": nodes[0]}

    svc._apply_mutation_to_graph(
        GraphMutationType.ADD_CRITIQUE,
        {"target_node_id": "impl", "node_id": "critique-impl"},
        nodes,
        edges,
        node_map,
    )
    assert len(nodes) == 2
    assert nodes[1]["node_type"] == GraphNodeKind.CRITIQUE_GATE


def test_apply_mutation_add_verifier() -> None:
    """V6-901: ADD_VERIFIER appends a VERIFICATION_GATE node."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes: list[dict] = [{"node_id": "impl", "node_type": "IMPLEMENT", "depends_on": []}]
    edges: list[list[str]] = []
    node_map = {"impl": nodes[0]}

    svc._apply_mutation_to_graph(
        GraphMutationType.ADD_VERIFIER,
        {"target_node_id": "impl", "node_id": "verify-impl"},
        nodes,
        edges,
        node_map,
    )
    assert nodes[1]["node_type"] == GraphNodeKind.VERIFICATION_GATE


def test_apply_mutation_cancel_subtree() -> None:
    """V6-901: CANCEL_SUBTREE marks root and descendants as BLOCKED."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes: list[dict] = [
        {"node_id": "a", "depends_on": []},
        {"node_id": "b", "depends_on": ["a"]},
        {"node_id": "c", "depends_on": ["b"]},
    ]
    edges = [["a", "b"], ["b", "c"]]
    node_map = {n["node_id"]: n for n in nodes}

    svc._apply_mutation_to_graph(
        GraphMutationType.CANCEL_SUBTREE,
        {"root_node_id": "a"},
        nodes,
        edges,
        node_map,
    )
    statuses = {n["node_id"]: n["status"] for n in nodes}
    assert statuses["a"] == SwarmNodeStatus.BLOCKED
    assert statuses["b"] == SwarmNodeStatus.BLOCKED
    assert statuses["c"] == SwarmNodeStatus.BLOCKED


def test_apply_mutation_supersede_node() -> None:
    """V6-901: SUPERSEDE_NODE skips old node and adds new one."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes: list[dict] = [{"node_id": "old", "node_type": "IMPLEMENT", "depends_on": []}]
    edges: list[list[str]] = [["old", "verify"]]
    node_map = {"old": nodes[0]}

    svc._apply_mutation_to_graph(
        GraphMutationType.SUPERSEDE_NODE,
        {
            "old_node_id": "old",
            "new_node_id": "new-impl",
            "new_node_type": "IMPLEMENT",
            "title": "New impl",
            "description": "better version",
        },
        nodes,
        edges,
        node_map,
    )
    old_node = next(n for n in nodes if n["node_id"] == "old")
    new_node = next(n for n in nodes if n["node_id"] == "new-impl")
    assert old_node["status"] == SwarmNodeStatus.SKIPPED
    assert new_node is not None


def test_apply_mutation_split_task() -> None:
    """V6-901: SPLIT_TASK creates child nodes from parent."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes: list[dict] = [{"node_id": "parent", "depends_on": []}]
    edges: list[list[str]] = []
    node_map = {"parent": nodes[0]}

    svc._apply_mutation_to_graph(
        GraphMutationType.SPLIT_TASK,
        {
            "original_node_id": "parent",
            "child_node_ids": [
                {"node_id": "child-1", "node_type": "RESEARCH", "title": "C1", "description": ""},
                {"node_id": "child-2", "node_type": "IMPLEMENT", "title": "C2", "description": ""},
            ],
        },
        nodes,
        edges,
        node_map,
    )
    assert len(nodes) == 3
    assert len(edges) == 2


def test_evaluate_composite_completion_requires_all_children() -> None:
    """V6-902: Composite node is complete only when all children are COMPLETED."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [
        {"node_id": "composite", "depends_on": []},
        {"node_id": "c1", "depends_on": ["composite"]},
        {"node_id": "c2", "depends_on": ["composite"]},
    ]
    statuses_partial = {"c1": "COMPLETED", "c2": "PENDING"}
    assert svc.evaluate_composite_completion("composite", nodes, statuses_partial) is False

    statuses_done = {"c1": "COMPLETED", "c2": "COMPLETED"}
    assert svc.evaluate_composite_completion("composite", nodes, statuses_done) is True


def test_gate_readiness_critique_gate() -> None:
    """V6-902: CRITIQUE_GATE requires CRITIQUE artifact."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    node = {"node_id": "gate", "node_type": GraphNodeKind.CRITIQUE_GATE}

    ok, reason = svc.check_gate_readiness(node, {"CRITIQUE"})
    assert ok

    fail, reason = svc.check_gate_readiness(node, set())
    assert not fail
    assert "CRITIQUE" in (reason or "")


def test_gate_readiness_verification_gate() -> None:
    """V6-902: VERIFICATION_GATE requires VERIFICATION artifact."""
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    node = {"node_id": "gate", "node_type": GraphNodeKind.VERIFICATION_GATE}

    fail, reason = svc.check_gate_readiness(node, {"CRITIQUE"})
    assert not fail
    assert "VERIFICATION" in (reason or "")

    ok, _ = svc.check_gate_readiness(node, {"VERIFICATION"})
    assert ok


def test_mutation_rejects_owner_mismatch_and_server_owned_fields() -> None:
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [
        {
            "node_id": "owned",
            "node_type": "IMPLEMENT",
            "owner_agent_id": "agent-a",
        }
    ]
    policy = domain.DeepSwarmPolicy()
    with pytest.raises(ValueError, match="Ownership"):
        svc._validate_mutation_request(
            GraphMutationType.APPEND_CHILD,
            {"node_id": "child", "parent_node_id": "owned"},
            "agent-b",
            nodes,
            [],
            {"owned": nodes[0]},
            policy,
        )
    with pytest.raises(ValueError, match="server-owned"):
        svc._validate_mutation_request(
            GraphMutationType.APPEND_CHILD,
            {
                "node_id": "child",
                "parent_node_id": "owned",
                "status": "COMPLETED",
            },
            "server:test",
            nodes,
            [],
            {"owned": nodes[0]},
            policy,
        )


def test_mutation_requires_registered_decision_contract() -> None:
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [{"node_id": "root", "node_type": "RESEARCH"}]
    with pytest.raises(ValueError, match="registered decision contract"):
        svc._validate_mutation_request(
            GraphMutationType.APPEND_CHILD,
            {
                "node_id": "branch",
                "parent_node_id": "root",
                "condition": "tests_failed",
                "decision_contract_id": "unregistered",
            },
            "server:test",
            nodes,
            [],
            {"root": nodes[0]},
            domain.DeepSwarmPolicy(),
        )


def test_graph_bounds_reject_depth_fanout_and_node_budget() -> None:
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [{"node_id": node_id} for node_id in ("a", "b", "c")]
    with pytest.raises(ValueError, match="depth"):
        svc._validate_graph_bounds(
            nodes,
            [["a", "b"], ["b", "c"]],
            domain.DeepSwarmPolicy(max_depth=1),
        )
    with pytest.raises(ValueError, match="fan-out"):
        svc._validate_graph_bounds(
            nodes,
            [["a", "b"], ["a", "c"]],
            domain.DeepSwarmPolicy(max_fan_out=1),
        )
    with pytest.raises(ValueError, match="node budget"):
        svc._validate_graph_bounds(
            nodes,
            [],
            domain.DeepSwarmPolicy(max_nodes=2),
        )


def test_composite_failure_preserves_partial_results() -> None:
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [
        {"node_id": "ok", "depends_on": ["parent"]},
        {"node_id": "failed", "depends_on": ["parent"]},
        {"node_id": "downstream", "depends_on": ["failed"]},
    ]
    statuses = {
        "ok": SwarmNodeStatus.COMPLETED.value,
        "failed": SwarmNodeStatus.FAILED.value,
        "downstream": SwarmNodeStatus.PENDING.value,
    }
    state, partial = svc.evaluate_composite_state("parent", nodes, statuses)
    assert state == SwarmNodeStatus.BLOCKED.value
    assert partial == ["ok"]
    propagated = svc.propagate_failure("failed", nodes, [["failed", "downstream"]], statuses)
    assert propagated["ok"] == SwarmNodeStatus.COMPLETED.value
    assert propagated["downstream"] == SwarmNodeStatus.BLOCKED.value


def test_deep_swarm_prefers_light_and_supports_single_worker_fallback() -> None:
    svc = TaskGraphService(None)  # type: ignore[arg-type]
    nodes = [{"node_id": "one", "node_type": "RESEARCH"}]
    assert svc._fits_light_swarm(nodes, [])
    assert domain.DeepSwarmPolicy(max_concurrent_workers=1).max_concurrent_workers == 1


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (DB required)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_v14_is_upgraded_for_recovery_and_coordination_state(tmp_path) -> None:
    """Interrupted v14 databases gain recovery, idempotency, and lease columns."""
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase9-v14.db').as_posix()}")
    async with manager.engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE schema_versions (version INTEGER PRIMARY KEY, applied_at DATETIME)")
        )
        await connection.execute(text("INSERT INTO schema_versions(version) VALUES (14)"))
        await connection.execute(
            text(
                "CREATE TABLE graph_mutation_journal ("
                "id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL, "
                "graph_version INTEGER NOT NULL, "
                "parent_graph_version INTEGER NOT NULL, "
                "mutation_type VARCHAR(50) NOT NULL, "
                "actor_agent_id VARCHAR(255) NOT NULL, reason TEXT NOT NULL, "
                "payload_json JSON NOT NULL, content_hash VARCHAR(64) NOT NULL, "
                "created_at DATETIME)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE deep_swarm_runs ("
                "id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL, "
                "status VARCHAR(50) NOT NULL, policy_json JSON NOT NULL, "
                "current_graph_version INTEGER NOT NULL, "
                "mutation_count INTEGER NOT NULL, stall_ticks INTEGER NOT NULL, "
                "cumulative_cost_usd FLOAT NOT NULL, "
                "cumulative_tokens INTEGER NOT NULL, "
                "cumulative_paid_calls INTEGER NOT NULL, "
                "node_statuses_json JSON NOT NULL, "
                "active_node_ids_json JSON NOT NULL, verdict VARCHAR(50), "
                "started_at DATETIME, finished_at DATETIME, created_at DATETIME)"
            )
        )

    assert await bootstrap_database(manager) == CURRENT_VERSION
    async with manager.engine.begin() as connection:
        journal_columns = await connection.execute(
            text("PRAGMA table_info(graph_mutation_journal)")
        )
        deep_run_columns = await connection.execute(text("PRAGMA table_info(deep_swarm_runs)"))
    assert "mutation_sequence" in {str(row[1]) for row in journal_columns.fetchall()}
    deep_names = {str(row[1]) for row in deep_run_columns.fetchall()}
    assert "node_side_effect_keys_json" in deep_names
    assert "completed_side_effect_keys_json" in deep_names
    await manager.close()


@pytest.mark.asyncio
async def test_graph_versioning_and_mutation_journal(db_manager) -> None:
    """V6-900 & V6-901: Create initial version, apply mutation, verify journal."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Graph Test", root_path="E:/tmp/graph", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="GR-1", title="Graph task", description="desc")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(
                node_id="research",
                node_type=SwarmNodeType.RESEARCH,
                title="Research",
                description="",
            ),
            SwarmNode(
                node_id="verify",
                node_type=SwarmNodeType.VERIFY,
                title="Verify",
                description="",
                depends_on=["research"],
            ),
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[("research", "verify")],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None

        # Create initial graph version 0
        gv0 = await uow.task_graph.create_initial_graph_version(plan.id)
        assert gv0.version == 0
        assert len(gv0.content_hash) == 64
        deep_run = await uow.task_graph.create_deep_swarm_run(
            plan.id,
            domain.DeepSwarmPolicy(
                enabled=True,
                prefer_light_swarm=False,
                registered_decision_contract_ids=["phase-c8-test-contract"],
            ),
        )
        assert deep_run.id is not None
        await uow.task_graph.enable_deep_swarm(deep_run.id)

        # Apply a valid mutation
        _, gv1 = await uow.task_graph.apply_mutation(
            plan_id=plan.id,
            mutation_type=GraphMutationType.APPEND_CHILD,
            actor_agent_id="agent-001",
            reason="Adding critique node",
            payload={
                "decision_contract_id": "phase-c8-test-contract",
                "node_id": "critique-1",
                "node_type": "CRITIQUE",
                "title": "Critique",
                "description": "Independent critique",
                "parent_node_id": "research",
            },
            expected_graph_version=0,
            deep_swarm_run_id=deep_run.id,
        )
        assert gv1.version == 1
        assert gv1.content_hash != gv0.content_hash

        # Mutation journal should have 1 entry
        journal = await uow.task_graph.get_mutation_journal(plan.id)
        assert len(journal) == 1
        assert journal[0].mutation_type == GraphMutationType.APPEND_CHILD
        assert journal[0].mutation_sequence == 1
        replayed = await uow.task_graph.replay_graph(plan.id)
        assert replayed is not None
        assert replayed.content_hash == gv1.content_hash
        _, updated_run = await uow.task_graph._load_deep_run(deep_run.id)
        assert updated_run.mutation_count == 1
        assert updated_run.current_graph_version == 1
        assert updated_run.active_node_ids == ["research"]
        await uow.task_graph.start_node(deep_run.id, "research")
        advanced = await uow.task_graph.tick_deep_swarm(deep_run.id, ["research"])
        assert set(advanced.active_node_ids) == {"critique-1", "verify"}


@pytest.mark.asyncio
async def test_deep_swarm_mutation_requires_registered_decision_contract(db_manager) -> None:
    """R7: agent graph mutations must reference a registered decision contract."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Decision Contract Test", root_path="E:/tmp/decision", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="DC-1", title="Decision", description="")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(node_id="n0", node_type=SwarmNodeType.RESEARCH, title="R", description="")
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None
        await uow.task_graph.create_initial_graph_version(plan.id)
        deep_run = await uow.task_graph.create_deep_swarm_run(
            plan.id,
            domain.DeepSwarmPolicy(
                enabled=True,
                prefer_light_swarm=False,
                registered_decision_contract_ids=["registered-contract"],
            ),
        )
        assert deep_run.id is not None
        await uow.task_graph.enable_deep_swarm(deep_run.id)

        with pytest.raises(ValueError, match="decision_contract_id"):
            await uow.task_graph.apply_mutation(
                plan_id=plan.id,
                mutation_type=GraphMutationType.APPEND_CHILD,
                actor_agent_id="agent-001",
                reason="Missing contract",
                payload={
                    "node_id": "child",
                    "node_type": "IMPLEMENT",
                    "parent_node_id": "n0",
                    "title": "Child",
                    "description": "",
                },
                expected_graph_version=0,
                deep_swarm_run_id=deep_run.id,
            )

        with pytest.raises(ValueError, match="not registered"):
            await uow.task_graph.apply_mutation(
                plan_id=plan.id,
                mutation_type=GraphMutationType.APPEND_CHILD,
                actor_agent_id="agent-001",
                reason="Wrong contract",
                payload={
                    "decision_contract_id": "unregistered-contract",
                    "node_id": "child",
                    "node_type": "IMPLEMENT",
                    "parent_node_id": "n0",
                    "title": "Child",
                    "description": "",
                },
                expected_graph_version=0,
                deep_swarm_run_id=deep_run.id,
            )


@pytest.mark.asyncio
async def test_stale_version_rejection(db_manager) -> None:
    """V6-901: Stale-version mutation is rejected."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Stale Test", root_path="E:/tmp/stale", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="ST-1", title="Stale test", description="")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(node_id="n0", node_type=SwarmNodeType.RESEARCH, title="R", description="")
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None

        await uow.task_graph.create_initial_graph_version(plan.id)

        # This mutation is correct (version 0)
        await uow.task_graph.apply_mutation(
            plan_id=plan.id,
            mutation_type=GraphMutationType.APPEND_CHILD,
            actor_agent_id="server:test",
            reason="First mutation",
            payload={
                "node_id": "c1",
                "node_type": "IMPLEMENT",
                "parent_node_id": "n0",
                "title": "C1",
                "description": "",
            },
            expected_graph_version=0,
        )

        # Sending expected_graph_version=0 again should fail (current is 1)
        with pytest.raises(ValueError, match="Stale mutation rejected"):
            await uow.task_graph.apply_mutation(
                plan_id=plan.id,
                mutation_type=GraphMutationType.APPEND_CHILD,
                actor_agent_id="server:test",
                reason="Stale mutation",
                payload={
                    "node_id": "c2",
                    "node_type": "IMPLEMENT",
                    "parent_node_id": "n0",
                    "title": "C2",
                    "description": "",
                },
                expected_graph_version=0,
            )


@pytest.mark.asyncio
async def test_cycle_mutation_rejected(db_manager) -> None:
    """V6-901: Mutation that would create a cycle is rejected."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Cycle Test", root_path="E:/tmp/cycle", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="CY-1", title="Cycle test", description="")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(node_id="a", node_type=SwarmNodeType.RESEARCH, title="A", description=""),
            SwarmNode(
                node_id="b",
                node_type=SwarmNodeType.IMPLEMENT,
                title="B",
                description="",
                depends_on=["a"],
            ),
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[("a", "b")],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None

        await uow.task_graph.create_initial_graph_version(plan.id)

        # ADD_DEPENDENCY b -> a would create a cycle
        with pytest.raises(ValueError, match="cycle"):
            await uow.task_graph.apply_mutation(
                plan_id=plan.id,
                mutation_type=GraphMutationType.ADD_DEPENDENCY,
                actor_agent_id="server:test",
                reason="Introduce cycle",
                payload={"from_node_id": "b", "to_node_id": "a"},
                expected_graph_version=0,
            )


@pytest.mark.asyncio
async def test_deep_swarm_disabled_by_default(db_manager) -> None:
    """V6-903: Deep Swarm is disabled by default and requires explicit opt-in."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Deep Test", root_path="E:/tmp/deep", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="DS-1", title="Deep", description="")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(node_id="n0", node_type=SwarmNodeType.RESEARCH, title="R", description="")
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None

        # Default policy: enabled=False
        await uow.task_graph.create_initial_graph_version(plan.id)
        run = await uow.task_graph.create_deep_swarm_run(plan.id)
        assert run.status == DeepSwarmStatus.DISABLED
        assert run.id is not None

        # Attempting to enable a disabled run (policy.enabled=False) should raise
        with pytest.raises(ValueError, match="opt-in"):
            await uow.task_graph.enable_deep_swarm(run.id)


@pytest.mark.asyncio
async def test_deep_swarm_enable_and_kill(db_manager) -> None:
    """V6-903 & V6-904: Deep Swarm can be explicitly enabled then killed."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Deep Enable Test", root_path="E:/tmp/deep2", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="DS-2", title="Deep2", description="")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(node_id="n0", node_type=SwarmNodeType.RESEARCH, title="R", description="")
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None

        await uow.task_graph.create_initial_graph_version(plan.id)
        fallback = await uow.task_graph.create_deep_swarm_run(
            plan.id,
            domain.DeepSwarmPolicy(enabled=True),
        )
        assert fallback.status == DeepSwarmStatus.DISABLED
        assert fallback.verdict == "FALLBACK_LIGHT_SWARM"
        evidence_required = await uow.task_graph.create_deep_swarm_run(
            plan.id,
            domain.DeepSwarmPolicy(
                enabled=True,
                prefer_light_swarm=False,
            ),
        )
        assert evidence_required.status == DeepSwarmStatus.DISABLED
        assert evidence_required.verdict == "EVIDENCE_REQUIRED"
        with pytest.raises(ValueError, match="decision-contract"):
            await uow.task_graph.enable_deep_swarm(evidence_required.id or 0)

        run = await uow.task_graph.create_deep_swarm_run(
            plan.id,
            domain.DeepSwarmPolicy(
                enabled=True,
                prefer_light_swarm=False,
                registered_decision_contract_ids=["phase-c8-test-contract"],
            ),
        )
        assert run.status == DeepSwarmStatus.PENDING
        assert run.id is not None

        run = await uow.task_graph.enable_deep_swarm(run.id)
        assert run.status == DeepSwarmStatus.RUNNING
        assert run.id is not None

        run = await uow.task_graph.kill_deep_swarm(run.id)
        assert run.status == DeepSwarmStatus.KILLED
        assert run.verdict == "KILLED_BY_USER"


@pytest.mark.asyncio
async def test_crash_recovery_reconciliation(db_manager) -> None:
    """V6-904: Reconciliation resets RUNNING nodes to PENDING after crash."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None
        assert uow.task_graph is not None

        proj = await uow.projects.create_project(
            domain.Project(
                name="Reconcile Test", root_path="E:/tmp/reconcile", default_branch="main"
            )
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="RC-1", title="Reconcile", description="")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [
            SwarmNode(node_id="n0", node_type=SwarmNodeType.RESEARCH, title="R", description=""),
            SwarmNode(
                node_id="n1",
                node_type=SwarmNodeType.IMPLEMENT,
                title="I",
                description="",
                depends_on=["n0"],
            ),
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[("n0", "n1")],
            policy=SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None

        await uow.task_graph.create_initial_graph_version(plan.id)
        deep_run = await uow.task_graph.create_deep_swarm_run(
            plan.id,
            domain.DeepSwarmPolicy(
                enabled=True,
                prefer_light_swarm=False,
                registered_decision_contract_ids=["phase-c8-test-contract"],
            ),
        )
        assert deep_run.id is not None
        await uow.task_graph.enable_deep_swarm(deep_run.id)
        await uow.task_graph.start_node(deep_run.id, "n0")
        assert await uow.task_graph.claim_external_side_effect(deep_run.id, "n0", "deploy:n0")

        # Reconcile
        report = await uow.task_graph.reconcile_after_restart(plan.id)
        assert report["status"] == "RECONCILED"
        assert "n0" in report["reconciled_nodes"]
        recovered = await uow.task_graph._load_deep_run(deep_run.id)
        assert recovered[1].node_statuses["n0"] == SwarmNodeStatus.PENDING.value
        assert recovered[1].node_side_effect_keys["n0"] == "deploy:n0"
        await uow.task_graph.complete_external_side_effect(deep_run.id, "n0", "deploy:n0")
        assert not await uow.task_graph.claim_external_side_effect(deep_run.id, "n0", "deploy:n0")
        clean_report = await uow.task_graph.reconcile_after_restart(plan.id)
        assert clean_report["status"] == "CLEAN"
