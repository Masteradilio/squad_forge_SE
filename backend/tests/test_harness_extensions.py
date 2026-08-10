import pytest
from pydantic import ValidationError

from localforge.api.schemas import SkillRequest
from localforge.observability.tracer import OpenTelemetryTracer
from localforge.runtime.agent_harness import AgentHarness
from localforge.runtime.harness_state import HarnessState
from localforge.runtime.subagents import (
    HarnessStateSubagentStore,
    SubagentRegistry,
    SubagentSpec,
)
from localforge.safety.hooks import (
    FunctionalToolPolicy,
    ToolCall,
    ToolExecutionMode,
    ToolPolicyDecision,
)
from localforge.skills.executor import (
    SkillExecutionContext,
    SkillExecutionError,
    SkillExecutor,
)
from localforge.skills.registry import SkillDefinition, SkillRegistry

from test_agent_harness import FakeProvider


@pytest.mark.asyncio
async def test_agent_harness_emits_ordered_lifecycle_events_and_tool_hooks():
    tracer = OpenTelemetryTracer()
    after_calls: list[str] = []

    async def after(call, result, error):
        after_calls.append(call.name)

    harness = AgentHarness(
        tracer=tracer,
        tool_policy=FunctionalToolPolicy(after=after),
    )
    result = await harness.call(
        provider=FakeProvider(["ok"]),
        contract=harness.contract_for(role="Reviewer", method="review", max_retries=0),
        messages=[{"role": "user", "content": "review"}],
    )

    tool_result = await harness.execute_tool(
        ToolCall(name="read_file"),
        lambda: _async_value("content"),
        parent_span_id=result.span_id,
    )

    event_types = [event["event_type"] for event in tracer.get_events()]
    assert event_types[:6] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert tool_result == "content"
    assert after_calls == ["read_file"]


@pytest.mark.asyncio
async def test_tool_policy_can_block_before_executor_and_preserves_batch_order():
    executed: list[str] = []

    async def before(call):
        if call.name == "blocked":
            return ToolPolicyDecision(allowed=False, reason="policy denied")
        return None

    harness = AgentHarness(tool_policy=FunctionalToolPolicy(before=before))
    with pytest.raises(PermissionError, match="policy denied"):
        await harness.execute_tool(
            ToolCall(name="blocked"),
            lambda: _record_value(executed, "blocked"),
        )
    assert executed == []

    values = await harness.execute_tools(
        [
            ToolCall(name="a", execution_mode=ToolExecutionMode.SEQUENTIAL),
            ToolCall(name="b", execution_mode=ToolExecutionMode.SEQUENTIAL),
        ],
        {
            "a": lambda: _record_value(executed, "a"),
            "b": lambda: _record_value(executed, "b"),
        },
    )
    assert values == ["a", "b"]
    assert executed == ["a", "b"]


@pytest.mark.asyncio
async def test_harness_state_subagent_store_is_durable(tmp_path):
    state = HarnessState(tmp_path)
    first = SubagentRegistry(HarnessStateSubagentStore(state))
    record = first.register(
        SubagentSpec(id="sub-1", task="audit", role="Reviewer", max_turns=2)
    )
    first.complete(record.id, result={"ok": True}, evidence=["receipt-1"])

    second = SubagentRegistry(HarnessStateSubagentStore(HarnessState(tmp_path)))
    restored = second.get(record.id)
    assert restored is not None
    assert restored.result == {"ok": True}
    assert restored.evidence == ["receipt-1"]


@pytest.mark.asyncio
async def test_skill_executor_requires_allowlisted_handler_and_permissions(tmp_path):
    registry = SkillRegistry(str(tmp_path))
    instruction = registry.write_local(
        SkillDefinition(name="guide", purpose="Instructions only")
    )
    executor = SkillExecutor(registry)
    declarative = await executor.execute(instruction)
    assert declarative.status == "DECLARATIVE_ONLY"

    python_skill = registry.write_local(
        SkillDefinition(
            name="trusted",
            purpose="Allowlisted handler",
            runtime="python",
            entrypoint="trusted:run",
            permissions=["read_files"],
        )
    )

    async def handler(values):
        return values["answer"]

    executor = SkillExecutor(registry, {"trusted:run": handler})
    with pytest.raises(SkillExecutionError, match="ungranted"):
        await executor.execute(python_skill, SkillExecutionContext())
    result = await executor.execute(
        python_skill,
        SkillExecutionContext(granted_permissions=frozenset({"read_files"}), values={"answer": 7}),
    )
    assert result.value == 7

    with pytest.raises(ValidationError, match="entrypoint"):
        SkillRequest(name="invalid", purpose="bad", runtime="python")


async def _async_value(value):
    return value


async def _record_value(target: list[str], value: str):
    target.append(value)
    return value

