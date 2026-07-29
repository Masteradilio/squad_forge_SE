from enum import StrEnum


class DocumentKind(StrEnum):
    PRD = "prd"
    BACKLOG = "backlog"
    ARCHITECTURE = "architecture"
    POLICY = "policy"
    NOTE = "note"


class TaskStatus(StrEnum):
    BACKLOG = "BACKLOG"
    READY = "READY"
    CLAIMED = "CLAIMED"
    PLANNING = "PLANNING"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
    REVIEWING = "REVIEWING"
    PR_READY = "PR_READY"
    BLOCKED = "BLOCKED"
    FAILED_SAFE = "FAILED_SAFE"
    BLOCKED_NEEDS_HUMAN_REVIEW = "BLOCKED_NEEDS_HUMAN_REVIEW"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class AgentRole(StrEnum):
    CHIEF_ENGINEER = "ChiefEngineer"
    SCRUM_MASTER = "ScrumMaster"
    PLANNER = "Planner"
    SPECIFIER = "Specifier"
    CODER = "Coder"
    CLEANER = "Cleaner"
    TESTER = "Tester"
    FIXER = "Fixer"
    REVIEWER = "Reviewer"
    ARCHITECT = "Architect"
    HARDENER = "Hardener"
    QA = "QA"
    PR_WRITER = "PRWriter"
    SAFETY_AUDITOR = "SafetyAuditor"


class TaskSeniorityClass(StrEnum):
    CHIEF_ONLY = "chief_only"
    CHIEF_LED = "chief_led"
    LOCAL_ASSISTED = "local_assisted"
    LOCAL_ONLY = "local_only"
    DETERMINISTIC_ONLY = "deterministic_only"


class RunMode(StrEnum):
    INTERACTIVE = "interactive"
    UNATTENDED = "unattended"
    DRY_RUN = "dry_run"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BLOCKED_NEEDS_HUMAN_REVIEW = "BLOCKED_NEEDS_HUMAN_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class HandoffKind(StrEnum):
    PLAN = "plan"
    IMPLEMENTATION = "implementation"
    TEST_RESULT = "test_result"
    REVIEW = "review"
    REPAIR_REQUEST = "repair_request"
    PR_READY = "pr_ready"
    BLOCKER = "blocker"


class HandoffStatus(StrEnum):
    PENDING = "PENDING"
    CONSUMED = "CONSUMED"
    FAILED = "FAILED"


class ArtifactType(StrEnum):
    ROLE = "RoleArtifact"
    PLAN = "PlanArtifact"
    DIFF = "DiffArtifact"
    TEST = "TestArtifact"
    LINT = "LintArtifact"
    TYPECHECK = "TypecheckArtifact"
    RISK = "RiskArtifact"
    REVIEW = "ReviewArtifact"
    REPAIR = "RepairArtifact"
    PR = "PRArtifact"
    BLOCKER = "BlockerArtifact"
    REPLAY = "ReplayArtifact"


class MemoryRecordKind(StrEnum):
    STACK_FACT = "stack_fact"
    TEST_COMMAND = "test_command"
    USER_PREFERENCE = "user_preference"
    KNOWN_PITFALL = "known_pitfall"
    RESOLVED_BLOCKER = "resolved_blocker"
    MODEL_PERFORMANCE_NOTE = "model_performance_note"


class AuditEventActorType(StrEnum):
    SYSTEM = "system"
    AGENT = "agent"
    USER = "user"


class AuditEventType(StrEnum):
    STATE_CHANGE = "state_change"
    SAFETY_DECISION = "safety_decision"
    SYSTEM_EVENT = "system_event"


class ActionApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"


class ActionKind(StrEnum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    GIT_COMMAND = "git_command"
    CREATE_BRANCH = "create_branch"
    CREATE_COMMIT = "create_commit"
    CREATE_PR = "create_pr"
    NETWORK_REQUEST = "network_request"


class RuntimeStatus(StrEnum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class FailureClass(StrEnum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    MISSING_IMPORT = "MISSING_IMPORT"
    PUBLIC_API_MISMATCH = "PUBLIC_API_MISMATCH"
    FORBIDDEN_DEPENDENCY = "FORBIDDEN_DEPENDENCY"
    SEMANTIC_TEST_FAILURE = "SEMANTIC_TEST_FAILURE"
    VISUAL_MISMATCH = "VISUAL_MISMATCH"
    TIMEOUT = "TIMEOUT"
    EMPTY_DIFF = "EMPTY_DIFF"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"


class ChiefEngineerCallReason(StrEnum):
    ARCHITECTURE_PLAN = "ARCHITECTURE_PLAN"
    CONTRACT_FREEZE = "CONTRACT_FREEZE"
    TASK_RISK_CLASSIFICATION = "TASK_RISK_CLASSIFICATION"
    CONTRACT_CHANGE_REVIEW = "CONTRACT_CHANGE_REVIEW"
    HARD_FAILURE_TRIAGE = "HARD_FAILURE_TRIAGE"
    SEMANTIC_REPAIR_PLAN = "SEMANTIC_REPAIR_PLAN"
    FINAL_PR_REVIEW = "FINAL_PR_REVIEW"
    E2E_RETROSPECTIVE = "E2E_RETROSPECTIVE"


class SquadRole(StrEnum):
    PRODUCT_OWNER = "ProductOwner"
    CHIEF_ENGINEER = "ChiefEngineer"
    SCRUM_MASTER = "ScrumMaster"
    SENIOR_DEVELOPER = "SeniorDeveloper"
    DEVELOPER = "Developer"
    QA_ENGINEER = "QAEngineer"
    BUG_FIXER = "BugFixer"
    REVIEWER = "Reviewer"
    PR_WRITER = "PRWriter"
    SAFETY_AUDITOR = "SafetyAuditor"


class SeniorityClass(StrEnum):
    HUMAN = "Human"
    CHIEF_ONLY = "chief_only"
    CHIEF_LED = "chief_led"
    LOCAL_ASSISTED = "local_assisted"
    LOCAL_ONLY = "local_only"
    DETERMINISTIC_ONLY = "deterministic_only"


class LoopStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class LoopRunStatus(StrEnum):
    PENDING = "PENDING"
    TRIAGING = "TRIAGING"
    NO_OP = "NO_OP"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TriggerKind(StrEnum):
    MANUAL = "MANUAL"
    INTERVAL = "INTERVAL"
    CRON = "CRON"
    EVENT = "EVENT"


class ExecutionStrategy(StrEnum):
    SEQUENTIAL = "SEQUENTIAL"
    LIGHT_SWARM = "LIGHT_SWARM"
    DEEP_SWARM = "DEEP_SWARM"


class AutonomyLevel(StrEnum):
    L0_SIMULATE = "L0_SIMULATE"
    L1_INSPECT = "L1_INSPECT"
    L2_ISOLATED = "L2_ISOLATED"
    L3_UNATTENDED = "L3_UNATTENDED"


class LoopRunVerdict(StrEnum):
    PENDING = "PENDING"
    NO_OP = "NO_OP"
    ACTIONABLE = "ACTIONABLE"
    FAILED = "FAILED"


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    COOLDOWN = "COOLDOWN"
    HALF_OPEN = "HALF_OPEN"
    ESCALATED = "ESCALATED"


class CircuitScope(StrEnum):
    LOOP = "LOOP"
    RUN = "RUN"
    ITEM = "ITEM"
    TASK = "TASK"
    PROVIDER = "PROVIDER"


class ProgressSignal(StrEnum):
    PROGRESS = "PROGRESS"
    STAGNATION = "STAGNATION"
    REGRESSION = "REGRESSION"
    REPEATED_FAILURE = "REPEATED_FAILURE"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXEMPT = "EXEMPT"


class AutonomyEnforcementResult(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED_AUTONOMY_EXCEEDED = "DENIED_AUTONOMY_EXCEEDED"
    DENIED_SELF_VERIFICATION = "DENIED_SELF_VERIFICATION"
    DENIED_ROLE_SPOOFING = "DENIED_ROLE_SPOOFING"


class WorktreeAttemptStatus(StrEnum):
    ACTIVE = "ACTIVE"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    MERGED = "MERGED"
    STALE = "STALE"
    CLEANED = "CLEANED"
    CANCELLED = "CANCELLED"


class LeaseReleaseReason(StrEnum):
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    BREAKER_OPEN = "BREAKER_OPEN"
    DEADLOCK_VICTIM = "DEADLOCK_VICTIM"


class PathLeaseWaitStatus(StrEnum):
    WAITING = "WAITING"
    ACQUIRED = "ACQUIRED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    DEADLOCK_VICTIM = "DEADLOCK_VICTIM"


class RunnerHealthState(StrEnum):
    READY = "READY"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    DRAINING = "DRAINING"
    QUARANTINED = "QUARANTINED"


class RunnerLane(StrEnum):
    INLINE = "INLINE"
    BACKGROUND = "BACKGROUND"
    SANDBOX = "SANDBOX"
    ISOLATED = "ISOLATED"


class TypedArtifactType(StrEnum):
    PLAN = "PLAN"
    RESEARCH = "RESEARCH"
    PATCH = "PATCH"
    TEST_RESULT = "TEST_RESULT"
    CRITIQUE = "CRITIQUE"
    VERIFICATION = "VERIFICATION"
    FAILURE = "FAILURE"
    ESCALATION = "ESCALATION"


class SwarmStrategy(StrEnum):
    SINGLE_WORKER = "SINGLE_WORKER"  # baseline / fallback
    LIGHT = "LIGHT"  # 2-4 workers, 1 decomposition level


class SwarmNodeType(StrEnum):
    RESEARCH = "RESEARCH"
    IMPLEMENT = "IMPLEMENT"
    TEST = "TEST"
    CRITIQUE = "CRITIQUE"
    VERIFY = "VERIFY"


class SwarmNodeStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


class SwarmStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    KILLED = "KILLED"


class GraphMutationType(StrEnum):
    SPLIT_TASK = "SPLIT_TASK"
    APPEND_CHILD = "APPEND_CHILD"
    ADD_DEPENDENCY = "ADD_DEPENDENCY"
    ADD_CRITIQUE = "ADD_CRITIQUE"
    ADD_VERIFIER = "ADD_VERIFIER"
    SUPERSEDE_NODE = "SUPERSEDE_NODE"
    CANCEL_SUBTREE = "CANCEL_SUBTREE"


class GraphNodeKind(StrEnum):
    ATOMIC = "ATOMIC"  # single-runner unit (like Phase 8 SwarmNode)
    COMPOSITE = "COMPOSITE"  # aggregates child evidence; complete when all children complete
    CRITIQUE_GATE = "CRITIQUE_GATE"  # must receive CRITIQUE artifact to proceed
    VERIFICATION_GATE = "VERIFICATION_GATE"  # must receive VERIFICATION artifact → PR_READY


class DeepSwarmStatus(StrEnum):
    DISABLED = "DISABLED"  # default; opt-in only
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    EXPANDING = "EXPANDING"  # dynamic expansion in progress
    STALLED = "STALLED"  # no marginal progress detected
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    KILLED = "KILLED"


class MemoryFactCategory(StrEnum):
    OBSERVED_FACT = "OBSERVED_FACT"
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    FAILURE_PATTERN = "FAILURE_PATTERN"
    OUTCOME = "OUTCOME"
    HUMAN_INSTRUCTION = "HUMAN_INSTRUCTION"


class MemoryRelationType(StrEnum):
    RELATES_TO = "RELATES_TO"
    SUPERSEDES = "SUPERSEDES"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"
    VALIDATED_BY = "VALIDATED_BY"


class MemoryValidityStatus(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    SUPERSEDED = "SUPERSEDED"
    CONTRADICTED = "CONTRADICTED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    UNVERIFIED = "UNVERIFIED"
