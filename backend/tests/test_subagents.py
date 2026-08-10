from pathlib import Path

import pytest
from pydantic import ValidationError

from localforge.runtime.agent_harness import ContextBlock
from localforge.runtime.run_control import RunContinuationPolicy
from localforge.runtime.subagents import (
    InMemorySubagentStore,
    SubagentRegistry,
    SubagentSpec,
    SubagentStatus,
)


def _spec(
    subagent_id: str,
    *,
    parent_id: str | None = None,
    max_depth: int = 0,
) -> SubagentSpec:
    return SubagentSpec(
        id=subagent_id,
        parent_id=parent_id,
        task="bounded task",
        role="Reviewer",
        allowed_actions=["read_file"],
        context_blocks=[ContextBlock(name="task", content="scoped context")],
        max_depth=max_depth,
        max_turns=3,
        max_tokens=128,
    )


def test_subagent_bounds_and_self_parent_are_typed():
    with pytest.raises(ValidationError):
        SubagentSpec(id="x", task="task", role="role", max_depth=-1)
    with pytest.raises(ValidationError):
        SubagentSpec(id="x", task="task", role="role", max_turns=0)
    with pytest.raises(ValidationError):
        SubagentSpec(id="x", task="task", role="role", max_tokens=0)
    with pytest.raises(ValueError, match="own parent"):
        SubagentSpec(id="x", parent_id="x", task="task", role="role")


def test_registry_admits_typed_children_and_enforces_depth():
    store = InMemorySubagentStore()
    registry = SubagentRegistry(store)
    root = registry.register(_spec("root", max_depth=1))
    child = registry.register_child("root", _spec("child"))

    assert child.parent_id == root.id
    assert child.depth == 1
    assert child.status is SubagentStatus.PENDING
    assert registry.children("root")[0].id == "child"

    with pytest.raises(ValueError, match="max_depth"):
        registry.register_child("child", _spec("grandchild"))


def test_registry_lifecycle_is_terminal_and_preserves_evidence():
    registry = SubagentRegistry()
    record = registry.register(_spec("worker"))
    running = registry.start(record.id)
    completed = registry.complete(
        running.id,
        result={"summary": "done"},
        evidence=["pytest passed"],
    )

    assert completed.status is SubagentStatus.COMPLETED
    assert completed.result == {"summary": "done"}
    assert completed.evidence == ["pytest passed"]
    with pytest.raises(ValueError, match="Terminal"):
        registry.transition(record.id, SubagentStatus.FAILED)


def test_run_continuation_policy_checks_limits_pause_and_quality_gates(tmp_path: Path):
    pause_file = tmp_path / "pause"
    policy = RunContinuationPolicy(
        max_turns=3,
        max_wall_seconds=5,
        max_retries=2,
        pause_file=pause_file,
        quality_gate_names=["tests"],
    )

    assert policy.check_pause() is False
    assert policy.should_continue(0, 0, retries=0, quality_gates={"tests": True}) is True
    assert policy.should_continue(0, 0, retries=0, quality_gates={"tests": False}) is False
    assert policy.should_continue(3, 0, retries=0, quality_gates={"tests": True}) is False
    assert policy.should_continue(0, 5, retries=0, quality_gates={"tests": True}) is False
    assert policy.should_continue(0, 0, retries=2, quality_gates={"tests": True}) is False

    pause_file.touch()
    assert policy.check_pause() is True
    assert policy.should_continue(0, 0, retries=0, quality_gates={"tests": True}) is False
