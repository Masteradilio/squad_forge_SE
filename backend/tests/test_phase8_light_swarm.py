"""Phase 8 — Light Swarm test suite.

Covers V6-800 to V6-804:
- Max worker / depth limits (policy enforcement)
- DAG acyclicity validation
- Parallel non-overlapping node resolution
- Upstream failure propagation + downstream BLOCKED state
- Single-worker fallback (SINGLE_WORKER strategy)
- Pause and kill controls
"""

import pytest
from localforge.models import domain
from localforge.models.enums import (
    SwarmNodeStatus,
    SwarmNodeType,
    SwarmStatus,
    SwarmStrategy,
    TypedArtifactType,
)
from localforge.services.light_swarm import LightSwarmService
from localforge.storage import UnitOfWork

# ─────────────────────────────────────────────────────────────────────────────
# Helper fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_node(
    node_id: str, node_type: SwarmNodeType, depends_on: list[str] | None = None
) -> domain.SwarmNode:
    return domain.SwarmNode(
        node_id=node_id,
        node_type=node_type,
        title=f"Node {node_id}",
        description=f"Description for {node_id}",
        depends_on=depends_on or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Unit-level tests (no DB required)
# ─────────────────────────────────────────────────────────────────────────────


def test_policy_validation_rejects_too_many_implement_nodes() -> None:
    """V6-800: Policy rejects plans with > 4 IMPLEMENT nodes."""
    nodes = [_make_node(f"n{i}", SwarmNodeType.IMPLEMENT) for i in range(5)]
    nodes.append(
        _make_node("checker", SwarmNodeType.VERIFY, depends_on=[f"n{i}" for i in range(5)])
    )
    edges = [(f"n{i}", "checker") for i in range(5)]

    policy = domain.SwarmPolicy(require_independent_checker=True)
    plan = domain.SwarmPlan(project_id=1, task_run_id=1, nodes=nodes, edges=edges, policy=policy)

    service = LightSwarmService(None)  # type: ignore[arg-type]
    valid, reason = service.validate_plan(plan)
    assert not valid
    assert "IMPLEMENT nodes" in (reason or "")


def test_policy_validation_rejects_sub_swarms() -> None:
    """V6-800: Policy rejects allow_sub_swarms=True."""
    nodes = [
        _make_node("n0", SwarmNodeType.RESEARCH),
        _make_node("v0", SwarmNodeType.VERIFY, ["n0"]),
    ]
    policy = domain.SwarmPolicy(allow_sub_swarms=True)
    plan = domain.SwarmPlan(
        project_id=1, task_run_id=1, nodes=nodes, edges=[("n0", "v0")], policy=policy
    )

    service = LightSwarmService(None)  # type: ignore[arg-type]
    valid, reason = service.validate_plan(plan)
    assert not valid
    assert "sub-swarms" in (reason or "")


def test_dag_acyclicity_check() -> None:
    """V6-801: Cyclic DAG is rejected."""
    nodes = [
        _make_node("a", SwarmNodeType.RESEARCH, []),
        _make_node("b", SwarmNodeType.IMPLEMENT, ["a"]),
        _make_node("c", SwarmNodeType.TEST, ["b"]),
    ]
    # Introduce a cycle: c -> a
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    policy = domain.SwarmPolicy(require_independent_checker=False)
    plan = domain.SwarmPlan(project_id=1, task_run_id=1, nodes=nodes, edges=edges, policy=policy)

    service = LightSwarmService(None)  # type: ignore[arg-type]
    valid, reason = service.validate_plan(plan)
    assert not valid
    assert "cycle" in (reason or "").lower()


def test_valid_light_swarm_plan_passes_validation() -> None:
    """V6-800: A well-formed plan passes all policy checks."""
    nodes = [
        _make_node("research", SwarmNodeType.RESEARCH),
        _make_node("impl", SwarmNodeType.IMPLEMENT, ["research"]),
        _make_node("test", SwarmNodeType.TEST, ["impl"]),
        _make_node("verify", SwarmNodeType.VERIFY, ["test"]),
    ]
    edges = [("research", "impl"), ("impl", "test"), ("test", "verify")]
    policy = domain.SwarmPolicy()
    plan = domain.SwarmPlan(project_id=1, task_run_id=1, nodes=nodes, edges=edges, policy=policy)

    service = LightSwarmService(None)  # type: ignore[arg-type]
    valid, reason = service.validate_plan(plan)
    assert valid
    assert reason is None


def test_single_worker_strategy_accepted() -> None:
    """V6-801: SINGLE_WORKER strategy (fallback) is always accepted with one node."""
    nodes = [_make_node("solo", SwarmNodeType.IMPLEMENT)]
    policy = domain.SwarmPolicy(
        strategy=SwarmStrategy.SINGLE_WORKER, require_independent_checker=False
    )
    plan = domain.SwarmPlan(
        project_id=1,
        task_run_id=1,
        strategy=SwarmStrategy.SINGLE_WORKER,
        nodes=nodes,
        edges=[],
        policy=policy,
    )

    service = LightSwarmService(None)  # type: ignore[arg-type]
    valid, reason = service.validate_plan(plan)
    assert valid


def test_ready_node_resolution_respects_dependencies() -> None:
    """V6-802: Only nodes with all dependencies COMPLETED are READY."""
    service = LightSwarmService(None)  # type: ignore[arg-type]
    nodes = [
        _make_node("a", SwarmNodeType.RESEARCH),
        _make_node("b", SwarmNodeType.IMPLEMENT, ["a"]),
        _make_node("c", SwarmNodeType.VERIFY, ["a", "b"]),
    ]
    # Only "a" has no dependencies — should be READY from the start
    statuses: dict[str, str] = {"a": "PENDING", "b": "PENDING", "c": "PENDING"}
    ready = service._resolve_ready_nodes(nodes, statuses)
    assert ready == ["a"]

    # After "a" completes, "b" should be READY; "c" still not
    statuses["a"] = "COMPLETED"
    ready = service._resolve_ready_nodes(nodes, statuses)
    assert ready == ["b"]

    # After both complete, "c" is READY
    statuses["b"] = "COMPLETED"
    ready = service._resolve_ready_nodes(nodes, statuses)
    assert ready == ["c"]


# ─────────────────────────────────────────────────────────────────────────────
# DB-level integration tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_swarm_plan_create_start_complete_and_kill(db_manager) -> None:
    """V6-802 & V6-804: Create plan, start run, complete a node, then kill remaining."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Swarm Test", root_path="E:/tmp/swarm", default_branch="main")
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="SW-1", title="Swarm task", description="desc")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        nodes = [
            _make_node("research", SwarmNodeType.RESEARCH),
            _make_node("verify", SwarmNodeType.VERIFY, ["research"]),
        ]
        edges: list[tuple[str, str]] = [("research", "verify")]
        policy = domain.SwarmPolicy(require_independent_checker=False)

        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=edges,
            policy=policy,
        )
        assert plan.id is not None

        # Start swarm — "research" should be initially READY
        run = await uow.light_swarm.start_swarm(plan.id)
        assert run.status == SwarmStatus.RUNNING
        assert "research" in run.active_node_ids

        # Complete "research" — "verify" should become READY
        assert run.id is not None
        run = await uow.light_swarm.complete_node(run.id, "research", cost_usd=0.01, tokens=100)
        assert run.node_statuses["research"] == SwarmNodeStatus.COMPLETED
        assert "verify" in run.active_node_ids

        # Kill the swarm
        assert run.id is not None
        run = await uow.light_swarm.kill_swarm(run.id)
        assert run.status == SwarmStatus.KILLED
        assert run.verdict == "KILLED_BY_USER"


@pytest.mark.asyncio
async def test_fail_node_propagates_blocked_downstream(db_manager) -> None:
    """V6-802: Failing a node blocks all transitively downstream nodes."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None

        proj = await uow.projects.create_project(
            domain.Project(
                name="Swarm Fail Test", root_path="E:/tmp/swarm_fail", default_branch="main"
            )
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="SW-2", title="Fail test", description="desc")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        nodes = [
            _make_node("n0", SwarmNodeType.RESEARCH),
            _make_node("n1", SwarmNodeType.IMPLEMENT, ["n0"]),
            _make_node("n2", SwarmNodeType.VERIFY, ["n1"]),
        ]
        edges: list[tuple[str, str]] = [("n0", "n1"), ("n1", "n2")]
        policy = domain.SwarmPolicy(require_independent_checker=False, max_retries_per_node=1)

        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=edges,
            policy=policy,
        )
        assert plan.id is not None

        run = await uow.light_swarm.start_swarm(plan.id)
        assert run.id is not None

        # Exhaust retries for n0: attempt_count=1 == max_retries_per_node=1 -> fails
        run = await uow.light_swarm.fail_node(run.id, "n0", "test failure", attempt_count=1)

        assert run.node_statuses["n0"] == SwarmNodeStatus.FAILED
        # n1 and n2 must be BLOCKED due to upstream failure
        assert run.node_statuses["n1"] == SwarmNodeStatus.BLOCKED
        assert run.node_statuses["n2"] == SwarmNodeStatus.BLOCKED
        assert run.status == SwarmStatus.FAILED
        assert run.verdict == "NEEDS_REPAIR"


@pytest.mark.asyncio
async def test_light_swarm_required_artifact_blocks_pr_ready(db_manager) -> None:
    """C6/C7: manual node completion without declared evidence cannot be PR_READY."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.light_swarm is not None

        proj = await uow.projects.create_project(
            domain.Project(
                name="Swarm Evidence Test",
                root_path="E:/tmp/swarm_evidence",
                default_branch="main",
            )
        )
        assert proj.id is not None
        task = await uow.tasks.create_task(
            domain.Task(project_id=proj.id, key="SW-3", title="Evidence", description="desc")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        nodes = [
            domain.SwarmNode(
                node_id="verify",
                node_type=SwarmNodeType.VERIFY,
                title="Node verify",
                description="Requires verification evidence",
                output_artifact_type=TypedArtifactType.VERIFICATION,
            ),
        ]
        plan = await uow.light_swarm.create_plan(
            project_id=proj.id,
            task_run_id=task_run.id,
            nodes=nodes,
            edges=[],
            policy=domain.SwarmPolicy(require_independent_checker=False),
        )
        assert plan.id is not None
        run = await uow.light_swarm.start_swarm(plan.id)
        assert run.id is not None

        run = await uow.light_swarm.complete_node(run.id, "verify")

        assert run.status == SwarmStatus.FAILED
        assert run.verdict == "EVIDENCE_MISSING"
