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


class ExternalLoopEventRequest(BaseModel):
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


class RunnerRegisterRequest(BaseModel):
    runner_id: str
    name: str
    lane: str = "INLINE"
    tools: list[str] = Field(default_factory=list)
    supported_task_types: list[str] = Field(default_factory=list)
    max_concurrency: int = 4


class RunnerDispatchRequest(BaseModel):
    project_id: int
    task_run_id: int
    required_lane: str | None = None
    required_tools: list[str] = Field(default_factory=list)
    required_task_type: str | None = None


class TypedHandoffCreateRequest(BaseModel):
    project_id: int
    task_run_id: int
    producer_agent_id: str
    consumer_agent_id: str
    summary: str
    artifact_type: str = "RESEARCH"
    schema_version: str = "1.0"
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    tests_executed: list[str] = Field(default_factory=list)
    validation_results_json: dict[str, Any] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)


class SwarmNodeInput(BaseModel):
    node_id: str
    node_type: str
    title: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    required_input_artifact_type: str | None = None
    output_artifact_type: str | None = None


class SwarmPolicyInput(BaseModel):
    strategy: str = "LIGHT"
    max_workers: int = 4
    max_depth: int = 1
    max_duration_seconds: int = 3600
    max_cost_usd: float = 5.0
    max_tokens: int = 500_000
    max_files: int = 50
    max_retries_per_node: int = 3
    allow_sub_swarms: bool = False
    require_independent_checker: bool = True


class SwarmCreateRequest(BaseModel):
    project_id: int
    task_run_id: int
    strategy: str = "LIGHT"
    nodes: list[SwarmNodeInput] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)
    policy: SwarmPolicyInput = Field(default_factory=SwarmPolicyInput)
    auto_start: bool = True


class SwarmNodeCompleteRequest(BaseModel):
    artifact_id: int | None = None
    cost_usd: float = 0.0
    tokens: int = 0
    ownership_token: str | None = None
    worker_agent_id: str | None = None


class SwarmNodeFailRequest(BaseModel):
    reason: str
    attempt_count: int = 1
    ownership_token: str | None = None


class MemoryFactCreateRequest(BaseModel):
    project_id: int
    fact: str
    kind: str = "stack_fact"
    source: str = "manual"
    category: str = "OBSERVED_FACT"
    validity: str = "AUTHORITATIVE"
    confidence: float = 1.0
    pinned: bool = False
    repository: str | None = None
    run_id: int | None = None
    task_key: str | None = None
    attempt_number: int | None = None
    artifact_id: int | None = None
    verifier: str | None = None
    policy_scope: str | None = None
    tags: list[str] = Field(default_factory=list)


class MemoryRelationCreateRequest(BaseModel):
    source_fact_id: int
    target_fact_id: int
    relation_type: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class MemoryConsolidateRequest(BaseModel):
    project_id: int
    max_fact_age_days: int = 90
    deduplication_threshold: float = 0.95


class MemoryRetrieveRequest(BaseModel):
    project_id: int
    query: str
    task_key: str | None = None
    category: str | None = None
    validity: str | None = None
    limit: int = 5
