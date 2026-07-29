from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from localforge.models.enums import (
    ActionApprovalStatus,
    ActionKind,
    AgentRole,
    ArtifactType,
    AuditEventActorType,
    AuditEventType,
    ChiefEngineerCallReason,
    CircuitScope,
    CircuitState,
    DeepSwarmStatus,
    DocumentKind,
    GraphMutationType,
    HandoffKind,
    HandoffStatus,
    LeaseReleaseReason,
    MemoryFactCategory,
    MemoryRecordKind,
    MemoryRelationType,
    MemoryValidityStatus,
    ProgressSignal,
    RunMode,
    RunnerHealthState,
    RunnerLane,
    RunStatus,
    RuntimeStatus,
    SeniorityClass,
    SquadRole,
    SwarmNodeStatus,
    SwarmNodeType,
    SwarmStatus,
    SwarmStrategy,
    TaskRunStatus,
    TaskStatus,
    TypedArtifactType,
    VerificationStatus,
    WorktreeAttemptStatus,
)
from localforge.models.loop import (
    LoopDefinition,
    LoopItem,
    LoopRun,
    LoopStateSnapshot,
    LoopTrigger,
)

__all__ = [
    "LoopDefinition",
    "LoopItem",
    "LoopRun",
    "LoopStateSnapshot",
    "LoopTrigger",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str
    root_path: str
    default_branch: str
    remote_url: str | None = None
    localforge_config_path: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProductDocument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    kind: DocumentKind
    path: str
    content_hash: str
    imported_at: datetime = Field(default_factory=utc_now)
    parsed_summary: str | None = None


class Epic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    title: str
    summary: str
    source_document_id: int | None = None
    priority: int = 1
    status: str = "BACKLOG"
    acceptance_summary: str | None = None


class Task(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    epic_id: int | None = None
    key: str
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependency_task_ids: list[int] = Field(default_factory=list)
    risk_level: str = "low"  # low, medium, high
    status: TaskStatus = TaskStatus.BACKLOG
    assigned_agent_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str
    role: AgentRole
    model_profile_id: str
    active: bool = True
    max_concurrent_tasks: int = 1
    permissions_profile_id: str | None = None
    heartbeat_at: datetime | None = None
    current_task_id: int | None = None


class Run(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    mode: RunMode
    status: RunStatus = RunStatus.PENDING
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    initiated_by: str
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class TaskRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    run_id: int
    task_id: int
    status: TaskRunStatus = TaskRunStatus.PENDING
    worktree_path: str | None = None
    branch_name: str | None = None
    sandbox_id: str | None = None
    attempt_count: int = 1
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    final_summary: str | None = None


class PRReadyEvidence(BaseModel):
    """Typed, server-owned evidence contract required before a task can become PR_READY."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    evidence_schema: str = Field(default="localforge.pr_ready_evidence.v1", alias="schema")
    source: str
    task_run_id: int
    handoff_id: int
    maker_id: str
    checker_id: str
    maker_attempt_id: str
    checker_attempt_id: str
    pre_pr_gate: dict[str, Any]
    risk_verdict: dict[str, Any]
    safety_verdict: dict[str, Any]
    checks_executed: list[str]
    artifact_paths: list[str] = Field(default_factory=list)
    branch_name: str | None = None
    worktree_path: str | None = None
    source_commit: str
    target_commit: str
    diff_hash: str

    @field_validator(
        "source",
        "maker_id",
        "checker_id",
        "maker_attempt_id",
        "checker_attempt_id",
        "source_commit",
        "target_commit",
        "diff_hash",
    )
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("checks_executed")
    @classmethod
    def _require_checks(cls, value: list[str]) -> list[str]:
        checks = [item.strip() for item in value if item.strip()]
        if not checks:
            raise ValueError("at least one deterministic check is required")
        return checks

    @model_validator(mode="after")
    def _validate_contract(self) -> "PRReadyEvidence":
        if self.evidence_schema != "localforge.pr_ready_evidence.v1":
            raise ValueError("unsupported PR_READY evidence schema")
        if self.maker_id == self.checker_id:
            raise ValueError("maker_id and checker_id must be independent")
        if self.maker_attempt_id == self.checker_attempt_id:
            raise ValueError("maker_attempt_id and checker_attempt_id must be independent")
        if self.pre_pr_gate.get("passed") is not True:
            raise ValueError("pre_pr_gate.passed must be true")
        if self.risk_verdict.get("passed") is not True:
            raise ValueError("risk_verdict.passed must be true")
        if self.safety_verdict.get("passed") is not True:
            raise ValueError("safety_verdict.passed must be true")
        for field_name in ("source_commit", "target_commit", "diff_hash"):
            observed = self.pre_pr_gate.get(field_name)
            if observed is not None and str(observed) != getattr(self, field_name):
                raise ValueError(f"pre_pr_gate.{field_name} must match evidence")
        return self


class Handoff(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    task_run_id: int
    from_role: AgentRole
    to_role: AgentRole
    kind: HandoffKind
    payload_json: dict[str, Any] = Field(default_factory=dict)
    priority: int = 1
    status: HandoffStatus = HandoffStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    consumed_at: datetime | None = None


class Artifact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    task_run_id: int
    type: ArtifactType
    path: str
    content_hash: str
    summary: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ModelRoute(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    role: AgentRole
    provider: str = "localforge"
    model_profile_id: str
    endpoint_url: str | None = None
    fallback_model_profile_id: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ModelCallLedger(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    run_id: int | None = None
    task_id: int | None = None
    provider: str
    model: str
    reason: ChiefEngineerCallReason
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    status: str = "success"
    error_summary: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MemoryFact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    kind: MemoryRecordKind = MemoryRecordKind.STACK_FACT
    fact: str
    source: str = "manual"
    pinned: bool = False
    status: str = "active"
    tags: list[str] = Field(default_factory=list)
    # Provenance-aware extensions (Phase 10 / V6-1000)
    repository: str | None = None
    run_id: int | None = None
    task_key: str | None = None
    attempt_number: int | None = None
    artifact_id: int | None = None
    verifier: str | None = None
    validity: MemoryValidityStatus = MemoryValidityStatus.AUTHORITATIVE
    confidence: float = 1.0
    policy_scope: str | None = None
    category: MemoryFactCategory = MemoryFactCategory.OBSERVED_FACT
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryRelation(BaseModel):
    """Relationship between two memory facts (V6-1001)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    source_fact_id: int
    target_fact_id: int
    relation_type: MemoryRelationType
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MemoryRetentionPolicy(BaseModel):
    """Project-configurable retention and staleness policy (V6-1002)."""

    model_config = ConfigDict(from_attributes=True)

    max_fact_age_days: int = 90
    auto_expire_unverified: bool = True
    consolidation_enabled: bool = True
    deduplication_threshold: float = 0.95


class MemoryRetrievalFilter(BaseModel):
    """Structured search filters for operational memory (V6-1003)."""

    repository: str | None = None
    task_key: str | None = None
    file_path: str | None = None
    error_fingerprint: str | None = None
    provider: str | None = None
    policy_scope: str | None = None
    category: MemoryFactCategory | None = None
    validity: MemoryValidityStatus | None = None
    tags: list[str] = Field(default_factory=list)


class MemoryRetrievalBenchmarkResult(BaseModel):
    """Evaluation metrics for retrieval quality baseline (V6-1003)."""

    model_config = ConfigDict(from_attributes=True)

    total_queries: int = 0
    recall_at_k: float = 0.0
    mrr: float = 0.0  # Mean Reciprocal Rank
    latency_ms: float = 0.0
    zero_result_rate: float = 0.0
    stale_hit_rate: float = 0.0
    contradictory_hit_rate: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)


class Policy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    name: str
    rules: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    run_id: int | None = None
    task_id: int | None = None
    actor_type: AuditEventActorType
    actor_id: str | None = None
    event_type: AuditEventType
    payload_redacted: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ActionApproval(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    run_id: int | None = None
    task_id: int | None = None
    action_kind: ActionKind
    payload: dict[str, Any] = Field(default_factory=dict)
    purpose: str
    risk_level: str
    status: ActionApprovalStatus = ActionApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None
    decided_by: str | None = None


class TaskComment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_id: int
    author: str
    body: str
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RuntimeRegistration(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    runtime_id: str
    name: str
    kind: str = "local"
    status: RuntimeStatus = RuntimeStatus.ONLINE
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    heartbeat_at: datetime = Field(default_factory=utc_now)
    registered_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Squad(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    name: str
    purpose: str = ""
    roles: list[AgentRole] = Field(default_factory=list)
    agent_ids: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PricingSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    provider: str
    url: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    notes: str = ""


class ModelPricingSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    pricing_source_id: int
    model_name: str
    input_price_per_million: float
    output_price_per_million: float
    cached_input_price_per_million: float = 0.0
    is_manual: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class ModelCapability(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_name: str
    task_class: str
    success_count: int = 0
    failure_count: int = 0
    disqualified_until: datetime | None = None
    disqualification_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SquadRoleMetadata(BaseModel):
    role: SquadRole
    seniority_class: SeniorityClass
    responsibility: str
    default_agent_role: AgentRole


SQUAD_ROLE_METADATA: dict[SquadRole, SquadRoleMetadata] = {
    SquadRole.PRODUCT_OWNER: SquadRoleMetadata(
        role=SquadRole.PRODUCT_OWNER,
        seniority_class=SeniorityClass.HUMAN,
        responsibility="Supplies PRD, accepts/rejects PRs, resolves product tradeoffs",
        default_agent_role=AgentRole.PLANNER,
    ),
    SquadRole.CHIEF_ENGINEER: SquadRoleMetadata(
        role=SquadRole.CHIEF_ENGINEER,
        seniority_class=SeniorityClass.CHIEF_ONLY,
        responsibility="Plans sprint, freezes contracts, performs hard implementation, triages failures, reviews final PR readiness",
        default_agent_role=AgentRole.CHIEF_ENGINEER,
    ),
    SquadRole.SENIOR_DEVELOPER: SquadRoleMetadata(
        role=SquadRole.SENIOR_DEVELOPER,
        seniority_class=SeniorityClass.CHIEF_LED,
        responsibility="Implements complex UI, architecture, cross-file changes, large rewrites",
        default_agent_role=AgentRole.CODER,
    ),
    SquadRole.DEVELOPER: SquadRoleMetadata(
        role=SquadRole.DEVELOPER,
        seniority_class=SeniorityClass.LOCAL_ASSISTED,
        responsibility="Implements narrow files under frozen contracts",
        default_agent_role=AgentRole.CODER,
    ),
    SquadRole.QA_ENGINEER: SquadRoleMetadata(
        role=SquadRole.QA_ENGINEER,
        seniority_class=SeniorityClass.LOCAL_ASSISTED,
        responsibility="Writes/runs focused tests only within allowed files",
        default_agent_role=AgentRole.TESTER,
    ),
    SquadRole.BUG_FIXER: SquadRoleMetadata(
        role=SquadRole.BUG_FIXER,
        seniority_class=SeniorityClass.LOCAL_ASSISTED,
        responsibility="Repairs syntax/import/simple failures locally; escalates semantic/visual/context failures",
        default_agent_role=AgentRole.FIXER,
    ),
    SquadRole.REVIEWER: SquadRoleMetadata(
        role=SquadRole.REVIEWER,
        seniority_class=SeniorityClass.CHIEF_ONLY,
        responsibility="Performs final contract-aware PR review after deterministic gates",
        default_agent_role=AgentRole.REVIEWER,
    ),
    SquadRole.PR_WRITER: SquadRoleMetadata(
        role=SquadRole.PR_WRITER,
        seniority_class=SeniorityClass.LOCAL_ONLY,
        responsibility="Writes summaries, changelog drafts, PR body text",
        default_agent_role=AgentRole.PR_WRITER,
    ),
    SquadRole.SAFETY_AUDITOR: SquadRoleMetadata(
        role=SquadRole.SAFETY_AUDITOR,
        seniority_class=SeniorityClass.DETERMINISTIC_ONLY,
        responsibility="Enforces file, command, dependency, budget, and policy constraints",
        default_agent_role=AgentRole.SAFETY_AUDITOR,
    ),
}


class FailureFingerprint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error_type: str
    normalized_message: str
    fingerprint_hash: str
    file_location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttemptProgressRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_number: int
    test_signature: str
    diff_signature: str
    artifact_signature: str
    signal: ProgressSignal
    fingerprint_hash: str | None = None


class CircuitBreakerState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    scope: CircuitScope
    target_id: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    stagnation_count: int = 0
    fingerprint_counts: dict[str, int] = Field(default_factory=dict)
    last_fingerprint: str | None = None
    opened_at: datetime | None = None
    cooldown_until: datetime | None = None
    reason: str | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MakerCheckerVerification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_run_id: int
    maker_agent_id: str
    checker_agent_id: str
    status: VerificationStatus = VerificationStatus.PENDING
    tests_executed: list[str] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)
    deterministic_passed: bool = False
    checker_feedback: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AutonomyPolicyRule(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    autonomy_level: Any  # AutonomyLevel
    allow_file_write: bool
    allow_command_execution: bool
    allow_git_commit: bool
    allow_pr_ready: bool
    allow_auto_merge: bool = False


class WorktreeAttemptManifest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_id: int
    task_run_id: int
    attempt_number: int = 1
    worktree_path: str
    branch_name: str
    source_commit: str
    owner_agent_id: str
    expected_paths: list[str] = Field(default_factory=list)
    leases_held: list[str] = Field(default_factory=list)
    status: WorktreeAttemptStatus = WorktreeAttemptStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PathLease(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_run_id: int
    owner_id: str
    target_path: str
    normalized_target_path: str | None = None
    is_directory: bool = False
    ttl_seconds: int = 3600
    expires_at: datetime = Field(default_factory=utc_now)
    heartbeat_at: datetime = Field(default_factory=utc_now)
    attempt_number: int = 1
    worktree_path: str | None = None
    fencing_token: str
    release_reason: LeaseReleaseReason | None = None
    created_at: datetime = Field(default_factory=utc_now)


class RunnerCapability(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lane: RunnerLane = RunnerLane.INLINE
    tools: list[str] = Field(default_factory=list)
    supported_task_types: list[str] = Field(default_factory=list)
    max_concurrency: int = 4
    platform: str = "windows"
    has_network_access: bool = True
    has_model_access: bool = True


class RunnerPoolState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    runner_id: str
    name: str
    lane: RunnerLane = RunnerLane.INLINE
    health_state: RunnerHealthState = RunnerHealthState.READY
    active_tasks_count: int = 0
    max_concurrency: int = 4
    capabilities: RunnerCapability = Field(default_factory=RunnerCapability)
    success_rate: float = 1.0
    quarantine_reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RunnerDispatchLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_run_id: int
    selected_runner_id: str | None = None
    lease_token: str | None = None
    lease_owner_id: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    dispatch_status: str = "SUCCESS"  # SUCCESS, NO_COMPATIBLE_RUNNER, BACKPRESSURE_LIMITED
    ranking_scores_json: dict[str, float] = Field(default_factory=dict)
    rejection_reasons_json: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TypedHandoffArtifact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_run_id: int
    producer_agent_id: str
    consumer_agent_id: str
    artifact_type: TypedArtifactType = TypedArtifactType.RESEARCH
    schema_version: str = "1.0"
    summary: str
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    tests_executed: list[str] = Field(default_factory=list)
    validation_results_json: dict[str, Any] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)
    content_hash: str
    is_consumed: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class SwarmPolicy(BaseModel):
    """Immutable policy constraints for a Light Swarm execution."""

    model_config = ConfigDict(from_attributes=True)

    strategy: SwarmStrategy = SwarmStrategy.LIGHT
    max_workers: int = 4  # 2-4 workers (V6-800)
    max_depth: int = 1  # no recursive sub-swarms (V6-800)
    max_duration_seconds: int = 3600  # 1-hour aggregate time bound
    max_cost_usd: float = 5.0  # aggregate budget bound
    max_tokens: int = 500_000  # aggregate token bound
    max_files: int = 50  # files across all code-changing nodes
    max_retries_per_node: int = 3  # per-node retry bound
    allow_sub_swarms: bool = False  # always False in Light mode
    require_independent_checker: bool = True


class SwarmNode(BaseModel):
    """Single node in a swarm DAG — one unit of work for one runner."""

    model_config = ConfigDict(from_attributes=True)

    node_id: str  # local identifier within plan (e.g. "node-0")
    node_type: SwarmNodeType
    status: SwarmNodeStatus = SwarmNodeStatus.PENDING
    title: str
    description: str
    owner_agent_id: str | None = None
    runner_id: str | None = None
    worktree_path: str | None = None
    required_input_artifact_type: TypedArtifactType | None = None
    output_artifact_type: TypedArtifactType | None = None
    depends_on: list[str] = Field(default_factory=list)
    artifact_id: int | None = None
    attempt_count: int = 0
    error_reason: str | None = None


class SwarmPlan(BaseModel):
    """Server-owned, validated DAG plan for a Light Swarm execution."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    task_run_id: int
    strategy: SwarmStrategy = SwarmStrategy.LIGHT
    status: SwarmStatus = SwarmStatus.DRAFT
    policy: SwarmPolicy = Field(default_factory=SwarmPolicy)
    nodes: list[SwarmNode] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)
    paused_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SwarmRun(BaseModel):
    """Mutable execution state of a swarm — tracks active nodes, cost, and verdict."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    plan_id: int
    status: SwarmStatus = SwarmStatus.DRAFT

    active_node_ids: list[str] = Field(default_factory=list)
    cumulative_cost_usd: float = 0.0
    cumulative_tokens: int = 0
    node_statuses: dict[str, str] = Field(default_factory=dict)
    verdict: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class SwarmExecutionSummary(BaseModel):
    """Replayable summary exported after swarm completion."""

    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    run_id: int
    strategy: SwarmStrategy
    verdict: str | None
    nodes: list[SwarmNode]
    total_cost_usd: float
    total_tokens: int
    duration_seconds: float
    artifact_ids: list[int]
    created_at: datetime = Field(default_factory=utc_now)


# ─── Phase 9 — Server-Owned Dynamic Task DAG and Deep Swarm ──────────────── #


class GraphMutationEntry(BaseModel):
    """Append-only journal entry for a single validated graph mutation (V6-900)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    plan_id: int  # parent SwarmPlan this journal belongs to
    mutation_sequence: int  # append-only sequence scoped to the plan
    graph_version: int  # graph version after this mutation is applied
    parent_graph_version: int  # graph version this mutation was applied against
    mutation_type: GraphMutationType
    actor_agent_id: str
    reason: str
    payload_json: dict[str, Any] = Field(default_factory=dict)  # mutation-specific params
    content_hash: str  # SHA-256 of (graph_version, mutation_type, payload)
    created_at: datetime = Field(default_factory=utc_now)


class DeepSwarmPolicy(BaseModel):
    """Policy constraints for Deep Swarm — opt-in experimental (V6-903)."""

    model_config = ConfigDict(from_attributes=True)

    enabled: bool = False  # disabled by default
    max_depth: int = Field(default=3, ge=1, le=8)
    max_nodes: int = Field(default=20, ge=1, le=200)
    max_fan_out: int = Field(default=6, ge=1, le=32)
    max_concurrent_workers: int = Field(default=4, ge=1, le=16)
    max_mutations: int = Field(default=50, ge=1, le=500)
    max_paid_calls: int = Field(default=100, ge=0, le=10_000)
    max_duration_seconds: int = Field(default=7200, ge=1, le=86_400)
    max_cost_usd: float = Field(default=20.0, ge=0.0, le=10_000.0)
    # Prefer Light Swarm when task fits fixed decomposition
    prefer_light_swarm: bool = True
    registered_decision_contract_ids: list[str] = Field(default_factory=list)
    # Stall detection: how many ticks without completed nodes before STALLED
    stall_tick_threshold: int = 5


class TaskGraphVersion(BaseModel):
    """Versioned snapshot of the dynamic task graph state (V6-900)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    plan_id: int
    version: int  # monotonically increasing per plan
    nodes_snapshot_json: list[Any] = Field(default_factory=list)
    edges_snapshot_json: list[Any] = Field(default_factory=list)
    content_hash: str  # SHA-256 of canonical (nodes, edges) at this version
    mutation_id: int | None = None  # mutation that produced this version (None = initial)
    created_at: datetime = Field(default_factory=utc_now)


class DeepSwarmRun(BaseModel):
    """Execution state for a Deep Swarm run (V6-903, V6-904)."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    plan_id: int
    status: DeepSwarmStatus = DeepSwarmStatus.DISABLED
    policy: DeepSwarmPolicy = Field(default_factory=DeepSwarmPolicy)
    current_graph_version: int = 0
    mutation_count: int = 0
    stall_ticks: int = 0  # ticks without progress; compare to policy.stall_tick_threshold
    cumulative_cost_usd: float = 0.0
    cumulative_tokens: int = 0
    cumulative_paid_calls: int = 0
    node_statuses: dict[str, str] = Field(default_factory=dict)
    active_node_ids: list[str] = Field(default_factory=list)
    node_side_effect_keys: dict[str, str] = Field(default_factory=dict)
    completed_side_effect_keys: list[str] = Field(default_factory=list)
    verdict: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
