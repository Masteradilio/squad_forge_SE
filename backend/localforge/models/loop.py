from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict

from localforge.models.enums import (
    AutonomyLevel,
    ExecutionStrategy,
    LoopRunStatus,
    LoopRunVerdict,
    LoopStatus,
    TriggerKind,
)


class LoopTrigger(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: TriggerKind = TriggerKind.MANUAL
    schedule: str | None = None  # Interval string e.g. "5m" or cron string "0 * * * *"
    event_type: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LoopDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    project_id: int
    name: str
    repository_path: str
    enabled: bool = True
    status: LoopStatus = LoopStatus.IDLE
    trigger: LoopTrigger = Field(default_factory=LoopTrigger)
    detector: str = "default_triage"  # Triage detector identifier
    execution_strategy: ExecutionStrategy = ExecutionStrategy.SEQUENTIAL
    autonomy: AutonomyLevel = AutonomyLevel.L1_INSPECT
    max_budget_usd: float = 5.0
    safety_policy: dict[str, Any] = Field(default_factory=dict)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LoopRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    loop_id: int
    status: LoopRunStatus = LoopRunStatus.PENDING
    trigger_kind: TriggerKind = TriggerKind.MANUAL
    idempotency_key: str
    triage_verdict: LoopRunVerdict = LoopRunVerdict.PENDING
    scheduler_run_id: int | None = None
    items_processed: int = 0
    cost_usd: float = 0.0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None


class LoopItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    loop_run_id: int
    external_id: str
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "PENDING"  # e.g. PENDING, ACTIONABLE, NO_OP, COMPLETED, FAILED
    scheduler_task_id: int | None = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LoopStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    loop_id: int
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active_run_id: int | None = None
    last_run_at: datetime | None = None
    next_eligible_run_at: datetime | None = None
    circuit_status: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    total_runs: int = 0
    total_cost_usd: float = 0.0
