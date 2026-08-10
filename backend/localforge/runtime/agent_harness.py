"""Shared, bounded execution contracts for every ForgeOS agent.

This module deliberately implements the useful ideas behind typed agent
methods without importing a third-party agent runtime.  It is an orchestration
layer only: generated content is returned to ForgeOS gateways and is never
executed here.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
import json
from typing import Any, TypeVar, cast

from pydantic import BaseModel, Field

from localforge.llm.base import BaseLLMProvider, LLMError, LLMMessage
from localforge.llm.validator import chat_completion_validated
from localforge.observability.tracer import OpenTelemetryTracer
from localforge.runtime.harness_state import HarnessState
from localforge.safety.hooks import (
    ToolCall,
    ToolExecutionMode,
    ToolPolicyHooks,
    evaluate_after,
    evaluate_before,
)


class AgentStrategy(StrEnum):
    PREDICT = "predict"
    CODE_ACT = "code_act"


class ContextBlock(BaseModel):
    """A named piece of context with explicit retention priority."""

    name: str
    content: str
    priority: int = Field(default=50, ge=0, le=100)
    required: bool = False
    max_chars: int | None = Field(default=None, ge=128)


class AgentMethodContract(BaseModel):
    """Typed metadata for one bounded model-backed agent method."""

    name: str
    role: str
    strategy: AgentStrategy
    max_retries: int = Field(default=1, ge=0, le=3)
    context_budget: int = Field(default=12000, ge=1000, le=50000)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None


class AgentCallResult(BaseModel):
    """Evidence returned by one harness method invocation."""

    content: str
    parsed: Any | None = None
    attempt_count: int = Field(default=1, ge=1)
    strategy: AgentStrategy
    context_blocks: list[str] = Field(default_factory=list)
    span_id: str
    parent_span_id: str | None = None


T = TypeVar("T", bound=BaseModel)


class _CountingProvider(BaseLLMProvider):
    """Provider decorator used to make validation retries observable."""

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider
        self.calls = 0
        self.provider_name = getattr(provider, "provider_name", "unknown")
        self.default_model = getattr(provider, "default_model", None)

    async def list_models(self) -> list[str]:
        return await self.provider.list_models()

    async def chat_completion(
        self,
        messages: list[LLMMessage],
        response_schema: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> str | AsyncIterator[str]:
        self.calls += 1
        return await self.provider.chat_completion(
            messages=messages,
            response_schema=response_schema,
            stream=stream,
            timeout=timeout,
            model=model,
        )


def select_agent_strategy(
    role: str,
    *,
    risk_level: str = "low",
    override: str | AgentStrategy | None = None,
) -> AgentStrategy:
    """Select a deterministic strategy without allowing arbitrary execution.

    Predict is the economical default for planning, review and documentation.
    CodeAct-like is reserved for roles that produce bounded runtime proposals;
    the resulting proposals still pass through ForgeOS safety gateways.
    """

    if override and str(override).lower() != "auto":
        return AgentStrategy(str(override).lower())
    normalized = role.lower().replace("_", " ").replace("-", " ")
    if normalized in {
        "coder",
        "developer",
        "cleaner",
        "tester",
        "qa",
        "fixer",
        "hardener",
    }:
        return AgentStrategy.CODE_ACT
    if normalized in {"chief engineer", "architect"} and risk_level.lower() == "high":
        return AgentStrategy.PREDICT
    return AgentStrategy.PREDICT


def compact_context(
    blocks: list[ContextBlock],
    *,
    budget: int,
) -> tuple[str, list[str]]:
    """Render required blocks first, then fill remaining context by priority.

    ``budget`` is expressed in approximate tokens. Required blocks are never
    discarded; optional blocks are truncated or omitted deterministically.
    """

    char_budget = max(4000, budget * 4)
    ordered = sorted(blocks, key=lambda block: (-int(block.required), -block.priority, block.name))
    rendered: list[str] = []
    included: list[str] = []
    used = 0
    for block in ordered:
        content = block.content.strip()
        if block.max_chars is not None:
            content = content[: block.max_chars]
        if not content:
            continue
        header = f"[{block.name}]\n"
        candidate = header + content
        if not block.required and used + len(candidate) > char_budget:
            remaining = char_budget - used
            if remaining <= len(header) + 128:
                continue
            candidate = header + content[: remaining - len(header) - 24].rstrip() + "\n[context compacted]"
        rendered.append(candidate)
        included.append(block.name)
        used += len(candidate) + 2
        if used >= char_budget and not block.required:
            break
    return "\n\n".join(rendered), included


async def _consume_content(value: str | AsyncIterator[str]) -> str:
    if isinstance(value, str):
        return value
    chunks: list[str] = []
    stream = cast(AsyncIterator[str], value)
    async for chunk in stream:
        chunks.append(str(chunk))
    close = getattr(stream, "aclose", None)
    if callable(close):
        await close()
    return "".join(chunks)


class AgentHarness:
    """Execute typed, bounded agent methods through a provider."""

    def __init__(
        self,
        *,
        tracer: OpenTelemetryTracer | None = None,
        tool_policy: ToolPolicyHooks | None = None,
        harness_state: HarnessState | None = None,
    ):
        self.tracer = tracer or OpenTelemetryTracer()
        self.tool_policy = tool_policy
        self.harness_state = harness_state

    def attach_harness_state(self, project_root: str) -> None:
        """Attach project-scoped supplemental context to future calls."""
        self.harness_state = HarnessState(project_root)

    def contract_for(
        self,
        *,
        role: str,
        method: str,
        risk_level: str = "low",
        strategy: str | AgentStrategy | None = None,
        max_retries: int = 1,
        context_budget: int = 12000,
    ) -> AgentMethodContract:
        return AgentMethodContract(
            name=method,
            role=role,
            strategy=select_agent_strategy(role, risk_level=risk_level, override=strategy),
            max_retries=max_retries,
            context_budget=context_budget,
        )

    async def call(
        self,
        *,
        provider: BaseLLMProvider,
        contract: AgentMethodContract,
        messages: list[LLMMessage],
        context_blocks: list[ContextBlock] | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        response_model: type[T] | None = None,
        stream: bool | None = None,
        parent_span_id: str | None = None,
    ) -> AgentCallResult:
        effective_blocks = list(context_blocks or [])
        if self.harness_state is not None:
            for entry in self.harness_state.list():
                effective_blocks.append(
                    ContextBlock(
                        name=f"harness:{entry.kind}:{entry.id}",
                        content=json.dumps(entry.content, ensure_ascii=False, default=str),
                        priority=40,
                        required=False,
                        max_chars=1200,
                    )
                )
        context_text, included_blocks = compact_context(
            effective_blocks, budget=contract.context_budget
        )
        call_messages = list(messages)
        if context_text:
            call_messages.append({"role": "user", "content": context_text})
        span = self.tracer.start_span(
            contract.role,
            contract.name,
            parent_span_id=parent_span_id,
            metadata={
                "strategy": contract.strategy.value,
                "model": model or getattr(provider, "default_model", None),
                "context_blocks": included_blocks,
            },
        )
        self.tracer.emit_event(
            "agent_start",
            span_id=span.span_id,
            payload={"strategy": contract.strategy.value},
        )
        self.tracer.emit_event("turn_start", span_id=span.span_id)
        self.tracer.emit_event(
            "message_start",
            span_id=span.span_id,
            payload={"message_count": len(call_messages)},
        )
        attempts = 1
        try:
            if response_model is not None:
                counting_provider = _CountingProvider(provider)
                parsed = await chat_completion_validated(
                    provider=counting_provider,
                    messages=call_messages,
                    schema_model=response_model,
                    max_retries=contract.max_retries,
                    timeout=timeout,
                    model=model,
                    stream=stream,
                )
                attempts = counting_provider.calls
                content = parsed.model_dump_json()
                self.tracer.emit_event(
                    "message_end",
                    span_id=span.span_id,
                    payload={"validated": True, "attempt_count": attempts},
                )
                self.tracer.emit_event(
                    "turn_end",
                    span_id=span.span_id,
                    payload={"attempt_count": attempts},
                )
                self.tracer.end_span(span.span_id, status="SUCCESS")
                self.tracer.emit_event(
                    "agent_end",
                    span_id=span.span_id,
                    payload={"status": "SUCCESS"},
                )
                return AgentCallResult(
                    content=content,
                    parsed=parsed.model_dump(mode="json"),
                    attempt_count=attempts,
                    strategy=contract.strategy,
                    context_blocks=included_blocks,
                    span_id=span.span_id,
                    parent_span_id=parent_span_id,
                )

            last_error: Exception | None = None
            for attempt in range(contract.max_retries + 1):
                attempts = attempt + 1
                try:
                    raw = await asyncio.wait_for(
                        provider.chat_completion(
                            messages=call_messages,
                            response_schema=contract.output_schema,
                            stream=False,
                            timeout=timeout,
                            model=model,
                        ),
                        timeout=timeout,
                    )
                    content = await _consume_content(raw)
                    if not content.strip():
                        raise LLMError("Agent method returned an empty response.")
                    self.tracer.emit_event(
                        "message_end",
                        span_id=span.span_id,
                        payload={"validated": False, "attempt_count": attempts},
                    )
                    self.tracer.emit_event(
                        "turn_end",
                        span_id=span.span_id,
                        payload={"attempt_count": attempts},
                    )
                    self.tracer.end_span(span.span_id, status="SUCCESS")
                    self.tracer.emit_event(
                        "agent_end",
                        span_id=span.span_id,
                        payload={"status": "SUCCESS"},
                    )
                    return AgentCallResult(
                        content=content,
                        attempt_count=attempts,
                        strategy=contract.strategy,
                        context_blocks=included_blocks,
                        span_id=span.span_id,
                        parent_span_id=parent_span_id,
                    )
                except Exception as exc:  # bounded retry is part of the contract
                    last_error = exc
                    if attempt < contract.max_retries:
                        self.tracer.emit_event(
                            "retry",
                            span_id=span.span_id,
                            payload={"attempt": attempts, "error": str(exc)[:300]},
                        )
                        await asyncio.sleep(min(0.05 * (2**attempt), 0.2))
            raise LLMError(
                f"Agent method {contract.role}.{contract.name} failed after {attempts} attempts: "
                f"{last_error}"
            ) from last_error
        except Exception:
            self.tracer.end_span(span.span_id, status="FAILED")
            self.tracer.emit_event(
                "agent_end",
                span_id=span.span_id,
                payload={"status": "FAILED", "attempt_count": attempts},
            )
            raise

    async def execute_tool(
        self,
        call: ToolCall,
        executor: Callable[[], Awaitable[Any]],
        *,
        parent_span_id: str | None = None,
    ) -> Any:
        """Run one tool through hooks while preserving ForgeOS safety gates.

        The executor remains responsible for calling ``ActionGateway`` and
        the Safety Kernel for file, command, network, or Git operations.
        """

        span = self.tracer.start_span(
            "tool",
            call.name,
            parent_span_id=parent_span_id,
            metadata={"execution_mode": call.execution_mode.value},
        )
        self.tracer.emit_event(
            "tool_execution_start",
            span_id=span.span_id,
            payload={"tool": call.name, "call_id": call.call_id},
        )
        result: Any = None
        error: BaseException | None = None
        after_called = False
        try:
            await evaluate_before(self.tool_policy, call)
            result = await executor()
            after_called = True
            await evaluate_after(self.tool_policy, call, result=result)
            self.tracer.end_span(span.span_id, status="SUCCESS")
            self.tracer.emit_event(
                "tool_execution_end",
                span_id=span.span_id,
                payload={"tool": call.name, "status": "SUCCESS"},
            )
            return result
        except BaseException as exc:
            error = exc
            self.tracer.end_span(span.span_id, status="FAILED")
            self.tracer.emit_event(
                "tool_execution_end",
                span_id=span.span_id,
                payload={"tool": call.name, "status": "FAILED", "error": str(exc)[:300]},
            )
            raise
        finally:
            if error is not None and not after_called:
                await evaluate_after(self.tool_policy, call, result=result, error=error)

    async def execute_tools(
        self,
        calls: list[ToolCall],
        executors: Mapping[str, Callable[[], Awaitable[Any]]],
        *,
        parent_span_id: str | None = None,
    ) -> list[Any]:
        """Execute a batch concurrently unless any tool requires ordering."""

        if any(call.execution_mode == ToolExecutionMode.SEQUENTIAL for call in calls):
            results: list[Any] = []
            for call in calls:
                results.append(
                    await self.execute_tool(
                        call,
                        executors[call.name],
                        parent_span_id=parent_span_id,
                    )
                )
            return results
        return list(
            await asyncio.gather(
                *(
                    self.execute_tool(
                        call,
                        executors[call.name],
                        parent_span_id=parent_span_id,
                    )
                    for call in calls
                )
            )
        )
