"""Bounded hooks shared by agent tools and the authoritative safety gateway.

Hooks are an extension point, not a replacement for ``ActionGateway`` or the
Safety Kernel.  A hook can add policy, telemetry, or approval context, but a
tool remains subject to the existing ForgeOS safety decision.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ToolExecutionMode(StrEnum):
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True)
class ToolCall:
    """Validated description of one bounded tool invocation."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    execution_mode: ToolExecutionMode = ToolExecutionMode.PARALLEL


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool = True
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolPolicyHooks(Protocol):
    """Optional policy hooks invoked around a tool execution."""

    async def before_tool_call(self, call: ToolCall) -> ToolPolicyDecision | None:
        ...

    async def after_tool_call(
        self,
        call: ToolCall,
        *,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        ...


BeforeHook = Callable[[ToolCall], Awaitable[ToolPolicyDecision | None]]
AfterHook = Callable[[ToolCall, Any, BaseException | None], Awaitable[None]]


@dataclass
class FunctionalToolPolicy:
    """Small adapter useful for project-defined pre/post policy functions."""

    before: BeforeHook | None = None
    after: AfterHook | None = None

    async def before_tool_call(self, call: ToolCall) -> ToolPolicyDecision | None:
        if self.before is None:
            return None
        return await self.before(call)

    async def after_tool_call(
        self,
        call: ToolCall,
        *,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        if self.after is not None:
            await self.after(call, result, error)


class ToolPolicyDenied(PermissionError):
    """Raised when a supplemental tool policy blocks an invocation."""


async def evaluate_before(
    hooks: ToolPolicyHooks | None,
    call: ToolCall,
) -> ToolPolicyDecision:
    if hooks is None:
        return ToolPolicyDecision()
    decision = await hooks.before_tool_call(call)
    normalized = decision or ToolPolicyDecision()
    if not normalized.allowed:
        reason = normalized.reason or f"Tool policy blocked {call.name}"
        raise ToolPolicyDenied(reason)
    return normalized


async def evaluate_after(
    hooks: ToolPolicyHooks | None,
    call: ToolCall,
    *,
    result: Any = None,
    error: BaseException | None = None,
) -> None:
    if hooks is not None:
        await hooks.after_tool_call(call, result=result, error=error)

