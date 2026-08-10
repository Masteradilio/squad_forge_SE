"""Capability-allowlisted execution boundary for user-defined skills.

Skill manifests are never imported dynamically.  A deployment explicitly
registers trusted handlers, and every invocation remains subject to the
declared capability set and the caller's safety boundary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from localforge.skills.registry import SkillDefinition, SkillRegistry


SkillHandler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class SkillExecutionContext:
    project_id: int | None = None
    run_id: int | None = None
    task_id: int | None = None
    granted_permissions: frozenset[str] = frozenset()
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillExecutionResult:
    skill_name: str
    runtime: str
    status: str
    value: Any = None
    entrypoint: str | None = None


class SkillExecutionError(RuntimeError):
    """Raised when a manifest cannot be executed within its grant."""


class SkillExecutor:
    """Execute only explicitly registered, capability-scoped handlers."""

    def __init__(
        self,
        registry: SkillRegistry,
        handlers: Mapping[str, SkillHandler] | None = None,
    ) -> None:
        self.registry = registry
        self.handlers = dict(handlers or {})

    async def execute(
        self,
        skill: SkillDefinition | dict[str, Any] | str,
        context: SkillExecutionContext | None = None,
    ) -> SkillExecutionResult:
        definition = self.registry._resolve_skill(skill)
        self.registry.validate_executable(definition)
        context = context or SkillExecutionContext()
        required = frozenset(definition.permissions)
        missing = required - context.granted_permissions
        if missing:
            raise SkillExecutionError(
                f"skill {definition.name} requires ungranted permissions: "
                + ", ".join(sorted(missing))
            )
        if definition.runtime == "instruction":
            return SkillExecutionResult(
                skill_name=definition.name,
                runtime=definition.runtime,
                status="DECLARATIVE_ONLY",
            )
        assert definition.entrypoint is not None
        handler = self.handlers.get(definition.entrypoint)
        if handler is None:
            raise SkillExecutionError(
                f"skill entrypoint is not registered by this deployment: {definition.entrypoint}"
            )
        value = await handler(dict(context.values))
        return SkillExecutionResult(
            skill_name=definition.name,
            runtime=definition.runtime,
            status="EXECUTED",
            value=value,
            entrypoint=definition.entrypoint,
        )


__all__ = [
    "SkillExecutionContext",
    "SkillExecutionError",
    "SkillExecutionResult",
    "SkillExecutor",
]

