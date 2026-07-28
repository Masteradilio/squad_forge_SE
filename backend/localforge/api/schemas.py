from typing import Any

from pydantic import BaseModel, Field

from localforge.models.enums import AgentRole, MemoryRecordKind, RuntimeStatus, TaskStatus
from localforge.pipeline import PipelineMode


class ImportPRDRequest(BaseModel):
    path: str
    dry_run: bool = False


class TaskUpdateRequest(BaseModel):
    epic_id: int | None = None
    title: str
    description: str
    acceptance_criteria: list[str]
    dependency_task_ids: list[int]
    risk_level: str
    status: TaskStatus


class ModelRouteRequest(BaseModel):
    role: AgentRole
    provider: str = "localforge"
    model_profile_id: str
    endpoint_url: str | None = None
    fallback_model_profile_id: str | None = None


class MemoryFactRequest(BaseModel):
    fact: str
    kind: MemoryRecordKind = MemoryRecordKind.STACK_FACT
    source: str = "manual"
    pinned: bool = False
    status: str = "active"
    tags: list[str] = Field(default_factory=list)


class MemoryFactUpdateRequest(BaseModel):
    fact: str | None = None
    pinned: bool | None = None
    status: str | None = None
    tags: list[str] | None = None


class MemoryImportRequest(BaseModel):
    format: str = "json"
    payload: dict[str, Any] | str


class TaskCommentRequest(BaseModel):
    author: str = "user"
    body: str
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeRegistrationRequest(BaseModel):
    runtime_id: str
    name: str
    kind: str = "local"
    status: RuntimeStatus = RuntimeStatus.ONLINE
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeHeartbeatRequest(BaseModel):
    status: RuntimeStatus = RuntimeStatus.ONLINE
    metadata: dict[str, Any] | None = None


class SquadRequest(BaseModel):
    name: str
    purpose: str = ""
    roles: list[AgentRole] = Field(default_factory=list)
    agent_ids: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineRunRequest(BaseModel):
    mode: PipelineMode = PipelineMode.DEFAULT
    run_id: int | None = None
    task_run_id: int | None = None


class SkillRequest(BaseModel):
    name: str
    purpose: str
    triggers: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    enabled: bool = True


class WorktreeRevertRequest(BaseModel):
    checkpoint_hash: str


class PricingSourceCreateRequest(BaseModel):
    provider: str
    url: str
    notes: str = ""


class PricingSnapshotUpdateRequest(BaseModel):
    pricing_source_id: int
    model_name: str
    input_price_per_million: float
    output_price_per_million: float
    cached_input_price_per_million: float = 0.0


class LoopCreateRequest(BaseModel):
    name: str
    repository_path: str
    enabled: bool = True
    trigger_kind: str = "MANUAL"
    schedule: str | None = None
    event_type: str | None = None
    detector: str = "default_triage"
    execution_strategy: str = "SEQUENTIAL"
    autonomy: str = "L1_INSPECT"
    max_budget_usd: float = 5.0
    safety_policy: dict[str, Any] = Field(default_factory=dict)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)


class LoopTriggerRequest(BaseModel):
    trigger_kind: str = "MANUAL"
    idempotency_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CircuitBreakerResetRequest(BaseModel):
    scope: str
    target_id: str
    actor_id: str = "user"
    reason: str = "Manual reset requested via API"


class KillRunRequest(BaseModel):
    actor_id: str = "user"
    reason: str = "Manual kill requested via API"


class VerificationCreateRequest(BaseModel):
    project_id: int
    task_run_id: int
    maker_agent_id: str
    checker_agent_id: str


class VerificationSubmitRequest(BaseModel):
    checker_agent_id: str
    approved: bool
    deterministic_passed: bool
    tests_executed: list[str] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)
    feedback: str | None = None


class AutonomyEvaluateRequest(BaseModel):
    autonomy_level: str
    action_kind: str
    target: str | None = None


class PathLeaseAcquireRequest(BaseModel):
    project_id: int
    task_run_id: int
    owner_id: str
    target_path: str
    is_directory: bool = False
    ttl_seconds: int = 3600


class WorktreeManifestCreateRequest(BaseModel):
    project_id: int
    task_id: int
    task_run_id: int
    worktree_path: str
    branch_name: str
    source_commit: str
    owner_agent_id: str
    expected_paths: list[str] = Field(default_factory=list)
