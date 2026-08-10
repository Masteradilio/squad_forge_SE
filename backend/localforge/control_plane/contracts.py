from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TodoStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class GateStatus(StrEnum):
    OPEN = "OPEN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class TurnRoute(StrEnum):
    READY = "READY"
    WAIT = "WAIT"
    REPAIR = "REPAIR"
    REPLAN = "REPLAN"
    ASK = "ASK"
    BLOCKED = "BLOCKED"
    COMPLETE = "COMPLETE"


class TurnResultKind(StrEnum):
    VALIDATED_PROGRESS = "VALIDATED_PROGRESS"
    VALIDATED_COMPLETION = "VALIDATED_COMPLETION"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    WAIT = "WAIT"
    HOST_FAILURE = "HOST_FAILURE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    WRITEBACK_FAILED = "WRITEBACK_FAILED"
    QUOTA_SPEND_FAILED = "QUOTA_SPEND_FAILED"


class CapabilityProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class TaskSnapshot(BaseModel):
    """Small scheduler projection; it intentionally contains no model output."""

    model_config = ConfigDict(extra="forbid")

    todo_id: str
    title: str
    status: str
    dependencies: list[str] = Field(default_factory=list)


class GoalState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    vision: str
    non_negotiables: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    authority: dict[str, str] = Field(default_factory=dict)
    source_revision: str | None = None
    acceptance_target: str | None = None
    # Existing journals remain compatible and keep their historical
    # task-only completion semantics. New scheduler goals opt into the
    # server-owned release completion gate explicitly.
    requires_release_promotion: bool = False
    last_receipt_id: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    current_todo_id: str | None = None
    created_at: str = Field(default_factory=utc_iso)
    updated_at: str = Field(default_factory=utc_iso)


class TodoState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    todo_id: str
    title: str
    dependencies: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    status: TodoStatus = TodoStatus.PENDING
    owner: str | None = None
    current_turn_id: str | None = None
    lease_token: str | None = None
    lease_expires_at: str | None = None
    attempts: int = 0
    last_error: str | None = None
    next_retry_at: str | None = None
    updated_at: str = Field(default_factory=utc_iso)


class GateState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str
    name: str
    required: bool = True
    status: GateStatus = GateStatus.OPEN
    receipt_ids: list[str] = Field(default_factory=list)
    question: str = ""
    authority: str = "human"
    safe_default: str | None = None
    affected_todo_ids: list[str] = Field(default_factory=list)
    expires_at: str | None = None
    answer: str | None = None
    answer_receipt_id: str | None = None


class AgentIdentity(BaseModel):
    """Durable authority record for a bounded-turn worker."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    role: str
    capabilities: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    authority: str = "worker"
    active: bool = True
    registered_at: str = Field(default_factory=utc_iso)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    todo_id: str
    turn_id: str
    result_kind: TurnResultKind
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    source_revision: str | None = None
    content_hash: str
    validated_by: str
    idempotency_key: str
    created_at: str = Field(default_factory=utc_iso)


class RepairHandoff(BaseModel):
    """Typed Scrum Master -> Chief Engineer recovery handoff."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    todo_id: str
    diagnosis: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    authority: str = "scrum_master"
    status: str = "OPEN"
    created_at: str = Field(default_factory=utc_iso)


class ExternalSignal(BaseModel):
    """Deduplicated observation that may change the next bounded decision."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str
    signal_type: str
    source: str
    fingerprint: str
    payload: dict[str, Any] = Field(default_factory=dict)
    affected_todo_id: str | None = None
    acknowledged_at: str | None = None
    created_at: str = Field(default_factory=utc_iso)


class CapabilityProposal(BaseModel):
    """Reviewable self-evolution proposal kept outside active task state."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    capability: str
    description: str
    isolated_scope: list[str] = Field(default_factory=list)
    source_revision: str | None = None
    status: CapabilityProposalStatus = CapabilityProposalStatus.PROPOSED
    proposed_by: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_iso)
    updated_at: str = Field(default_factory=utc_iso)


class QuotaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns: int = 100
    turns_started: int = 0
    turns_committed: int = 0
    max_attempts_per_todo: int = 3
    max_cost_usd: float = 5.0
    cost_committed_usd: float = 0.0
    max_wall_seconds: float | None = None
    started_at: str = Field(default_factory=utc_iso)


class ControlPlaneState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    revision: int = 0
    goal: GoalState
    todos: list[TodoState] = Field(default_factory=list)
    gates: list[GateState] = Field(default_factory=list)
    agents: list[AgentIdentity] = Field(default_factory=list)
    receipts: list[Receipt] = Field(default_factory=list)
    handoffs: list[RepairHandoff] = Field(default_factory=list)
    signals: list[ExternalSignal] = Field(default_factory=list)
    quota: QuotaState = Field(default_factory=QuotaState)
    applied_operations: dict[str, int] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    capability_proposals: list[CapabilityProposal] = Field(default_factory=list)


class TurnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: TurnRoute
    reason: str
    revision: int
    todo_id: str | None = None
    turn_id: str | None = None
    lease_token: str | None = None
    wait_until: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)


class TurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    todo_id: str
    turn_id: str
    result_kind: TurnResultKind
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    validated_by: str
    idempotency_key: str
    changed_files: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    source_revision: str | None = None
    cost_usd: float = 0.0
