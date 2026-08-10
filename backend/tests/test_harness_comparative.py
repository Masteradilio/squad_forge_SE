"""Comparative scorecard for the pre-Harness path versus the current Harness.

The legacy profile intentionally models the behavior that existed before the
last two improvements: one provider call, no lifecycle events, no supplemental
tool policy, no durable state, and no bounded subagent admission.  It is not a
second production implementation.  Its purpose is to keep the comparison
explicit and deterministic while the current profile uses the real ForgeOS
contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from localforge.llm.base import BaseLLMProvider
from localforge.observability.tracer import OpenTelemetryTracer
from localforge.runtime.agent_harness import AgentHarness
from localforge.runtime.harness_state import HarnessEntry, HarnessState
from localforge.runtime.run_control import RunContinuationPolicy
from localforge.runtime.subagents import (
    SubagentRegistry,
    SubagentRegistryError,
    SubagentSpec,
)
from localforge.safety.hooks import (
    FunctionalToolPolicy,
    ToolCall,
    ToolPolicyDecision,
    ToolPolicyDenied,
)
from localforge.skills.executor import (
    SkillExecutionContext,
    SkillExecutionError,
    SkillExecutor,
)
from localforge.skills.registry import SkillDefinition, SkillRegistry


class Output(BaseModel):
    answer: str


class ScriptedProvider(BaseLLMProvider):
    provider_name = "comparative-fake"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0
        self.seen_messages: list[list[dict[str, Any]]] = []

    async def list_models(self) -> list[str]:
        return ["comparative-model"]

    async def chat_completion(
        self,
        messages,
        response_schema=None,
        stream=False,
        timeout=30.0,
        model=None,
    ):
        self.calls += 1
        self.seen_messages.append(list(messages))
        if not self.responses:
            raise AssertionError("scripted provider response queue exhausted")
        return self.responses.pop(0)


class LegacyAgentPath:
    """Small adapter representing the old one-shot execution semantics."""

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def call_once(self, messages: list[dict[str, str]]) -> Output | None:
        raw = await self.provider.chat_completion(messages)
        try:
            return Output.model_validate_json(raw)
        except (ValidationError, ValueError):
            return None

    async def execute_tool(self, executor):
        return await executor()


@dataclass(frozen=True)
class ScoreRow:
    capability: str
    legacy: int
    current: int
    evidence: str


@pytest.mark.asyncio
async def test_current_harness_scorecard_exceeds_pre_harness_profile(tmp_path: Path):
    rows: list[ScoreRow] = []

    # 1. Typed recovery: the old path gives up after its first malformed
    # response; AgentHarness performs the bounded validation retry.
    legacy_provider = ScriptedProvider(["not-json", '{"answer":"ok"}'])
    legacy_result = await LegacyAgentPath(legacy_provider).call_once(
        [{"role": "user", "content": "review"}]
    )
    current_provider = ScriptedProvider(["not-json", '{"answer":"ok"}'])
    current = AgentHarness()
    current_result = await current.call(
        provider=current_provider,
        contract=current.contract_for(role="Reviewer", method="review", max_retries=1),
        messages=[{"role": "user", "content": "review"}],
        response_model=Output,
    )
    assert legacy_result is None
    assert legacy_provider.calls == 1
    assert current_result.parsed == {"answer": "ok"}
    assert current_result.attempt_count == 2
    assert current_provider.calls == 2
    rows.append(
        ScoreRow(
            "recuperação de resposta estruturada",
            0,
            1,
            "legacy 1 chamada/sem recuperação; Harness 2 tentativas válidas",
        )
    )

    # 2. Lifecycle observability: the old caller could create a span, but had
    # no ordered agent/turn/message event stream.
    legacy_tracer = OpenTelemetryTracer()
    legacy_span = legacy_tracer.start_span("Reviewer", "review")
    legacy_tracer.end_span(legacy_span.span_id)
    current_tracer = OpenTelemetryTracer()
    await AgentHarness(tracer=current_tracer).call(
        provider=ScriptedProvider(["ok"]),
        contract=AgentHarness(tracer=current_tracer).contract_for(
            role="Reviewer", method="review", max_retries=0
        ),
        messages=[{"role": "user", "content": "review"}],
    )
    legacy_events = legacy_tracer.get_events()
    current_events = [event["event_type"] for event in current_tracer.get_events()]
    assert legacy_events == []
    assert current_events[:6] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    rows.append(
        ScoreRow(
            "telemetria ordenada do ciclo de vida",
            0,
            1,
            "legacy apenas span; Harness emite 6 eventos de ciclo",
        )
    )

    # 3. Supplemental tool policy: the old direct path executes the call;
    # the current path denies it before the executor is reached.
    legacy_executed: list[str] = []
    await LegacyAgentPath(ScriptedProvider(["unused"])).execute_tool(
        lambda: _record(legacy_executed, "dangerous")
    )
    current_executed: list[str] = []

    async def before(call: ToolCall):
        if call.name == "dangerous":
            return ToolPolicyDecision(allowed=False, reason="comparison policy")
        return None

    protected = AgentHarness(tool_policy=FunctionalToolPolicy(before=before))
    with pytest.raises(ToolPolicyDenied, match="comparison policy"):
        await protected.execute_tool(
            ToolCall(name="dangerous"),
            lambda: _record(current_executed, "dangerous"),
        )
    assert legacy_executed == ["dangerous"]
    assert current_executed == []
    rows.append(
        ScoreRow(
            "bloqueio pré-execução por política",
            0,
            1,
            "legacy executa; hook atual bloqueia antes do executor",
        )
    )

    # 4. Durable context: the old path has no project state to restore; the
    # current harness persists and injects the supplemental entry.
    legacy_state = HarnessState(tmp_path / "legacy")
    assert legacy_state.get("comparison-memory") is None
    current_state = HarnessState(tmp_path / "current")
    current_state.upsert(
        HarnessEntry(
            id="comparison-memory",
            kind="memory",
            scope="project",
            content={"decision": "keep evidence"},
        )
    )
    restored_state = HarnessState(tmp_path / "current")
    current_with_state = AgentHarness(harness_state=restored_state)
    state_result = await current_with_state.call(
        provider=ScriptedProvider(["state-aware"]),
        contract=current_with_state.contract_for(
            role="Reviewer", method="review", max_retries=0
        ),
        messages=[{"role": "user", "content": "review"}],
    )
    assert restored_state.get("comparison-memory") is not None
    assert "harness:memory:comparison-memory" in state_result.context_blocks
    rows.append(
        ScoreRow(
            "estado durável e contexto restaurável",
            0,
            1,
            "legacy sem entrada restaurável; Harness restaura e injeta memória",
        )
    )

    # 5. Bounded subagent admission: the old profile has no registry check;
    # the current registry rejects a child under a depth-zero parent.
    legacy_nested_depth = 0
    legacy_nested_depth += 1
    assert legacy_nested_depth == 1
    registry = SubagentRegistry()
    root = registry.register(
        SubagentSpec(id="comparison-root", task="root", role="Planner", max_depth=0)
    )
    with pytest.raises(SubagentRegistryError, match="max_depth=0"):
        registry.register_child(
            root.id,
            SubagentSpec(id="comparison-child", task="child", role="Reviewer"),
        )
    rows.append(
        ScoreRow(
            "admissão de subagente com limite",
            0,
            1,
            "legacy aceita profundidade; Registry atual rejeita além do limite",
        )
    )

    # 6. Pause/continuation: the old profile continues blindly; the current
    # pure policy stops on an external pause marker.
    pause_file = tmp_path / "pause.requested"
    policy = RunContinuationPolicy(max_turns=3, pause_file=pause_file)
    assert policy.should_continue(turns=0) is True
    pause_file.write_text("pause", encoding="utf-8")
    assert policy.should_continue(turns=0) is False
    legacy_should_continue = True
    assert legacy_should_continue is True
    rows.append(
        ScoreRow(
            "pausa determinística de continuidade",
            0,
            1,
            "legacy continua; policy atual respeita marcador de pausa",
        )
    )

    # 7. Executable skill boundary: the old registry was declarative only;
    # the current executor supports a trusted handler without dynamic import
    # and enforces the declared permission grant.
    registry = SkillRegistry(str(tmp_path / "skills"))
    skill = registry.write_local(
        SkillDefinition(
            name="comparison-skill",
            purpose="deterministic comparison",
            runtime="python",
            entrypoint="comparison:run",
            permissions=["read_files"],
        )
    )

    async def handler(values):
        return values["value"]

    executor = SkillExecutor(registry, {"comparison:run": handler})
    with pytest.raises(SkillExecutionError, match="ungranted"):
        await executor.execute(skill, SkillExecutionContext(values={"value": 7}))
    skill_result = await executor.execute(
        skill,
        SkillExecutionContext(
            granted_permissions=frozenset({"read_files"}),
            values={"value": 7},
        ),
    )
    assert skill_result.status == "EXECUTED"
    assert skill_result.value == 7
    rows.append(
        ScoreRow(
            "Skill executável com permissão explícita",
            0,
            1,
            "legacy declarativa; executor atual executa handler allowlisted",
        )
    )

    legacy_score = sum(row.legacy for row in rows)
    current_score = sum(row.current for row in rows)
    assert current_score > legacy_score
    assert current_score == len(rows)

    print("\nForgeOS Harness comparative scorecard")
    print("capability | legacy | current | evidence")
    for row in rows:
        print(f"{row.capability} | {row.legacy} | {row.current} | {row.evidence}")
    print(f"score | {legacy_score}/{len(rows)} | {current_score}/{len(rows)}")

async def _record(target: list[str], value: str):
    target.append(value)
    return value
