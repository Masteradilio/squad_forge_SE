import pytest
from pydantic import BaseModel

from localforge.llm.base import BaseLLMProvider
from localforge.observability.tracer import OpenTelemetryTracer
from localforge.runtime.agent_harness import (
    AgentHarness,
    AgentStrategy,
    ContextBlock,
    compact_context,
    select_agent_strategy,
)
from localforge.skills.registry import SkillDefinition, SkillRegistry


class FakeProvider(BaseLLMProvider):
    provider_name = "fake"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    async def list_models(self) -> list[str]:
        return ["fake-model"]

    async def chat_completion(self, messages, response_schema=None, stream=False, timeout=30.0, model=None):
        self.calls += 1
        if not self.responses:
            raise AssertionError("fake provider response queue exhausted")
        return self.responses.pop(0)


class Output(BaseModel):
    answer: str


def test_strategy_selection_is_deterministic_and_bounded():
    assert select_agent_strategy("Coder") is AgentStrategy.CODE_ACT
    assert select_agent_strategy("Reviewer") is AgentStrategy.PREDICT
    assert select_agent_strategy("Coder", override="predict") is AgentStrategy.PREDICT


def test_context_compaction_keeps_required_blocks():
    rendered, names = compact_context(
        [
            ContextBlock(name="optional", content="x" * 5000, priority=1),
            ContextBlock(name="contract", content="policy contract", required=True, priority=100),
        ],
        budget=1000,
    )
    assert "policy contract" in rendered
    assert "contract" in names
    assert len(rendered) < 5000


@pytest.mark.asyncio
async def test_typed_call_validates_and_bounds_retries():
    provider = FakeProvider(["not-json", '{"answer":"ok"}'])
    harness = AgentHarness()
    contract = harness.contract_for(role="Reviewer", method="review", max_retries=1)
    result = await harness.call(
        provider=provider,
        contract=contract,
        messages=[{"role": "user", "content": "review"}],
        response_model=Output,
    )
    assert result.parsed == {"answer": "ok"}
    assert result.attempt_count == 2
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_raw_call_retries_empty_response_and_records_nested_trace():
    tracer = OpenTelemetryTracer()
    harness = AgentHarness(tracer=tracer)
    parent_provider = FakeProvider(["plan"])
    parent = await harness.call(
        provider=parent_provider,
        contract=harness.contract_for(role="Scrum Master", method="plan", max_retries=0),
        messages=[{"role": "user", "content": "plan"}],
    )
    child_provider = FakeProvider(["", "actions"])
    child = await harness.call(
        provider=child_provider,
        contract=harness.contract_for(role="Coder", method="implement", max_retries=1),
        messages=[{"role": "user", "content": "implement"}],
        parent_span_id=parent.span_id,
    )
    assert child.content == "actions"
    assert child.attempt_count == 2
    assert child.parent_span_id == parent.span_id
    assert tracer.spans[-1].root_span_id == parent.span_id


def test_user_skill_persists_harness_profile_and_can_be_removed(tmp_path):
    registry = SkillRegistry(str(tmp_path))
    saved = registry.write_local(
        SkillDefinition(
            name="performance-specialist",
            purpose="Optimize performance",
            system_prompt="Use bounded profiling evidence.",
            strategy="predict",
            max_retries=2,
            context_budget=9000,
        )
    )
    loaded = registry.load_all()
    custom = next(skill for skill in loaded if skill.name == saved.name)
    assert custom.system_prompt == "Use bounded profiling evidence."
    assert custom.strategy == "predict"
    assert custom.max_retries == 2
    assert custom.context_budget == 9000
    assert custom.runtime == "instruction"
    assert registry.validate_executable(custom) is True
    assert registry.resolve_execution_manifest(custom) == {
        "name": "performance-specialist",
        "manifest_version": 1,
        "runtime": "instruction",
        "entrypoint": None,
        "permissions": [],
        "dependencies": [],
    }
    assert registry.delete_local(saved.name) is True


def test_python_skill_manifest_requires_entrypoint_and_is_not_executed(tmp_path):
    registry = SkillRegistry(str(tmp_path))
    with pytest.raises(ValueError, match="entrypoint"):
        SkillDefinition(
            name="python-skill",
            purpose="Declarative Python skill metadata.",
            runtime="python",
        )

    saved = registry.write_local(
        SkillDefinition(
            name="python-skill",
            purpose="Declarative Python skill metadata.",
            runtime="python",
            entrypoint="package.module:run",
            permissions=["read_files", "run_tests"],
            dependencies=["internal-package"],
            manifest_version=2,
        )
    )
    assert registry.resolve_execution_manifest(saved) == {
        "name": "python-skill",
        "manifest_version": 2,
        "runtime": "python",
        "entrypoint": "package.module:run",
        "permissions": ["read_files", "run_tests"],
        "dependencies": ["internal-package"],
    }
