"""Typed admission and lifecycle records for bounded harness subagents.

The registry in this module does not start workers, acquire leases, or execute
actions.  It records an admission decision and the lifecycle state that an
existing control-plane owner can project into its own execution model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from localforge.runtime.agent_harness import ContextBlock
from localforge.runtime.harness_state import HarnessEntry, HarnessState


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SubagentStatus(StrEnum):
    """Lifecycle states understood by the admission registry."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"

    @classmethod
    def _missing_(cls, value: object) -> SubagentStatus | None:
        """Accept case-insensitive status values at API boundaries."""

        if isinstance(value, str):
            normalized = value.strip().upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return None


TERMINAL_SUBAGENT_STATUSES = frozenset(
    {
        SubagentStatus.COMPLETED,
        SubagentStatus.FAILED,
        SubagentStatus.BLOCKED,
        SubagentStatus.CANCELLED,
    }
)


class SubagentRegistryError(ValueError):
    """Base error for rejected subagent admission or lifecycle operations."""


class SubagentNotFoundError(KeyError):
    """Raised when a parent or record is not present in the backing store."""


class SubagentSpec(BaseModel):
    """Immutable-by-convention admission data for one subagent record."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(default_factory=lambda: f"subagent-{uuid4().hex}", min_length=1)
    parent_id: str | None = None
    task: str = Field(min_length=1)
    role: str = Field(min_length=1)
    allowed_actions: list[str] = Field(default_factory=list)
    context_blocks: list[ContextBlock | dict[str, Any] | str] = Field(default_factory=list)
    max_depth: int = Field(default=0, ge=0)
    max_turns: int = Field(default=1, gt=0)
    max_tokens: int = Field(default=4096, gt=0)

    @model_validator(mode="after")
    def reject_self_parent(self) -> SubagentSpec:
        if self.parent_id is not None and self.parent_id == self.id:
            raise ValueError("A subagent cannot be its own parent.")
        return self


class SubagentRecord(SubagentSpec):
    """Stored admission data plus bounded lifecycle and evidence state."""

    depth: int = Field(default=0, ge=0)
    status: SubagentStatus = SubagentStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    result: Any | None = None
    evidence: list[Any] = Field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_SUBAGENT_STATUSES


class SubagentStore(Protocol):
    """Minimal persistence boundary required by :class:`SubagentRegistry`."""

    def get(self, subagent_id: str) -> SubagentRecord | None:
        """Return a record or ``None`` when it is absent."""

    def put(self, record: SubagentRecord) -> None:
        """Insert or replace a record by its id."""

    def list(self) -> list[SubagentRecord]:
        """Return records in the store's deterministic order."""


class InMemorySubagentStore:
    """Small process-local adapter useful for tests and ephemeral runtimes."""

    def __init__(self) -> None:
        self._records: dict[str, SubagentRecord] = {}

    def get(self, subagent_id: str) -> SubagentRecord | None:
        record = self._records.get(subagent_id)
        return record.model_copy(deep=True) if record is not None else None

    def put(self, record: SubagentRecord) -> None:
        self._records[record.id] = record.model_copy(deep=True)

    def list(self) -> list[SubagentRecord]:
        return [record.model_copy(deep=True) for record in self._records.values()]

    # ``save`` is a readable alias for callers that use repository terminology.
    def save(self, record: SubagentRecord) -> None:
        self.put(record)


class HarnessStateSubagentStore:
    """Durable adapter that stores records as supplemental HarnessState."""

    def __init__(self, state: HarnessState):
        self.state = state

    def get(self, subagent_id: str) -> SubagentRecord | None:
        entry = self.state.get(subagent_id)
        if entry is None or entry.kind != "subagent":
            return None
        return SubagentRecord.model_validate(entry.content)

    def put(self, record: SubagentRecord) -> None:
        self.state.upsert(
            HarnessEntry(
                id=record.id,
                kind="subagent",
                scope="project",
                content=record.model_dump(mode="json"),
                source="subagent_registry",
            )
        )

    def list(self) -> list[SubagentRecord]:
        return [
            SubagentRecord.model_validate(entry.content)
            for entry in self.state.list(kind="subagent")
        ]


_MISSING = object()


class SubagentRegistry:
    """Admit bounded child records and project their lifecycle state.

    ``max_depth`` is an inclusive depth bound for descendants of a record;
    roots have depth zero, so a record at its bound cannot register another
    child.  The registry never invokes an agent or an action.
    """

    terminal_statuses = TERMINAL_SUBAGENT_STATUSES

    def __init__(
        self,
        store: SubagentStore | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store: SubagentStore = store if store is not None else InMemorySubagentStore()
        self._clock = clock or _utc_now

    def register(self, spec: SubagentSpec) -> SubagentRecord:
        """Admit one root or parent-linked subagent specification."""

        if not isinstance(spec, SubagentSpec):
            raise TypeError("SubagentRegistry.register expects a SubagentSpec.")
        if self.store.get(spec.id) is not None:
            raise SubagentRegistryError(f"Subagent id already exists: {spec.id}")

        depth = 0
        if spec.parent_id is not None:
            parent = self._require(spec.parent_id)
            if spec.id == parent.id:
                raise SubagentRegistryError("A subagent cannot be its own parent.")
            if parent.depth >= parent.max_depth:
                raise SubagentRegistryError(
                    f"Parent {parent.id} has reached max_depth={parent.max_depth}."
                )
            depth = parent.depth + 1

        record = SubagentRecord(
            id=spec.id,
            parent_id=spec.parent_id,
            task=spec.task,
            role=spec.role,
            allowed_actions=list(spec.allowed_actions),
            context_blocks=list(spec.context_blocks),
            max_depth=spec.max_depth,
            max_turns=spec.max_turns,
            max_tokens=spec.max_tokens,
            depth=depth,
            status=SubagentStatus.PENDING,
            created_at=self._clock(),
            updated_at=self._clock(),
        )
        self.store.put(record)
        return record.model_copy(deep=True)

    def register_child(self, parent_id: str, spec: SubagentSpec) -> SubagentRecord:
        """Bind a specification to a known parent and admit it."""

        if spec.id == parent_id:
            raise SubagentRegistryError("A subagent cannot be its own parent.")
        if spec.parent_id is not None and spec.parent_id != parent_id:
            raise SubagentRegistryError(
                f"Subagent {spec.id} is already bound to parent {spec.parent_id}."
            )
        if spec.parent_id != parent_id:
            spec = spec.model_copy(update={"parent_id": parent_id})
        return self.register(spec)

    def get(self, subagent_id: str) -> SubagentRecord | None:
        """Return a defensive copy of one record, if present."""

        return self.store.get(subagent_id)

    def list(self, *, parent_id: str | None = None) -> list[SubagentRecord]:
        """List records, optionally restricted to direct children."""

        records = self.store.list()
        if parent_id is not None:
            records = [record for record in records if record.parent_id == parent_id]
        return [record.model_copy(deep=True) for record in records]

    def children(self, parent_id: str) -> list[SubagentRecord]:
        """Return direct children without implying execution or scheduling."""

        return self.list(parent_id=parent_id)

    def transition(
        self,
        subagent_id: str,
        status: SubagentStatus | str,
        *,
        result: Any = _MISSING,
        evidence: Iterable[Any] | None | object = _MISSING,
    ) -> SubagentRecord:
        """Record a lifecycle transition while preserving terminality."""

        record = self._require(subagent_id)
        if record.is_terminal:
            raise SubagentRegistryError(
                f"Terminal subagent {record.id} cannot transition from {record.status.value}."
            )

        next_status = SubagentStatus(status)
        updates: dict[str, Any] = {
            "status": next_status,
            "updated_at": self._clock(),
        }
        if result is not _MISSING:
            updates["result"] = result
        if evidence is not _MISSING:
            updates["evidence"] = [] if evidence is None else list(evidence)
        updated = record.model_copy(update=updates, deep=True)
        self.store.put(updated)
        return updated.model_copy(deep=True)

    def update_status(
        self,
        subagent_id: str,
        status: SubagentStatus | str,
        *,
        result: Any = _MISSING,
        evidence: Iterable[Any] | None | object = _MISSING,
    ) -> SubagentRecord:
        """Readable alias for :meth:`transition`."""

        return self.transition(subagent_id, status, result=result, evidence=evidence)

    def start(self, subagent_id: str) -> SubagentRecord:
        return self.transition(subagent_id, SubagentStatus.RUNNING)

    def pause(self, subagent_id: str) -> SubagentRecord:
        return self.transition(subagent_id, SubagentStatus.PAUSED)

    def resume(self, subagent_id: str) -> SubagentRecord:
        return self.transition(subagent_id, SubagentStatus.RUNNING)

    def complete(
        self,
        subagent_id: str,
        *,
        result: Any = None,
        evidence: Iterable[Any] | None = None,
    ) -> SubagentRecord:
        return self.transition(
            subagent_id,
            SubagentStatus.COMPLETED,
            result=result,
            evidence=evidence,
        )

    def fail(
        self,
        subagent_id: str,
        *,
        result: Any = None,
        evidence: Iterable[Any] | None = None,
    ) -> SubagentRecord:
        return self.transition(
            subagent_id,
            SubagentStatus.FAILED,
            result=result,
            evidence=evidence,
        )

    def block(
        self,
        subagent_id: str,
        *,
        result: Any = None,
        evidence: Iterable[Any] | None = None,
    ) -> SubagentRecord:
        return self.transition(
            subagent_id,
            SubagentStatus.BLOCKED,
            result=result,
            evidence=evidence,
        )

    def cancel(
        self,
        subagent_id: str,
        *,
        result: Any = None,
        evidence: Iterable[Any] | None = None,
    ) -> SubagentRecord:
        return self.transition(
            subagent_id,
            SubagentStatus.CANCELLED,
            result=result,
            evidence=evidence,
        )

    def _require(self, subagent_id: str) -> SubagentRecord:
        record = self.store.get(subagent_id)
        if record is None:
            raise SubagentNotFoundError(subagent_id)
        return record
