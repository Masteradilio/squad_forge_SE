from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from localforge.models import domain, enums



class Base(DeclarativeBase):
    pass


class SchemaVersionORM(Base):
    __tablename__ = "schema_versions"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False)
    remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    localforge_config_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.Project:
        return domain.Project.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Project) -> "ProjectORM":
        return cls(
            id=d.id,
            name=d.name,
            root_path=d.root_path,
            default_branch=d.default_branch,
            remote_url=d.remote_url,
            localforge_config_path=d.localforge_config_path,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class ProductDocumentORM(Base):
    __tablename__ = "product_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> domain.ProductDocument:
        return domain.ProductDocument.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.ProductDocument) -> "ProductDocumentORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            kind=d.kind,
            path=d.path,
            content_hash=d.content_hash,
            imported_at=d.imported_at,
            parsed_summary=d.parsed_summary,
        )


class EpicORM(Base):
    __tablename__ = "epics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_documents.id", ondelete="SET NULL"), nullable=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="BACKLOG")
    acceptance_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> domain.Epic:
        return domain.Epic.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Epic) -> "EpicORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            title=d.title,
            summary=d.summary,
            source_document_id=d.source_document_id,
            priority=d.priority,
            status=d.status,
            acceptance_summary=d.acceptance_summary,
        )


class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    epic_id: Mapped[int | None] = mapped_column(
        ForeignKey("epics.id", ondelete="SET NULL"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dependency_task_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="BACKLOG", nullable=False)
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.Task:
        # We need to map `metadata_json` to domain's `metadata`
        return domain.Task(
            id=self.id,
            project_id=self.project_id,
            epic_id=self.epic_id,
            key=self.key,
            title=self.title,
            description=self.description,
            acceptance_criteria=self.acceptance_criteria,
            dependency_task_ids=self.dependency_task_ids,
            risk_level=self.risk_level,
            status=domain.TaskStatus(self.status),
            assigned_agent_id=self.assigned_agent_id,
            metadata=self.metadata_json,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.Task) -> "TaskORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            epic_id=d.epic_id,
            key=d.key,
            title=d.title,
            description=d.description,
            acceptance_criteria=d.acceptance_criteria,
            dependency_task_ids=d.dependency_task_ids,
            risk_level=d.risk_level,
            status=d.status.value,
            assigned_agent_id=d.assigned_agent_id,
            metadata_json=d.metadata,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class AgentORM(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    model_profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=1)
    permissions_profile_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def to_domain(self) -> domain.Agent:
        return domain.Agent.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Agent) -> "AgentORM":
        return cls(
            id=d.id,
            name=d.name,
            role=d.role.value,
            model_profile_id=d.model_profile_id,
            active=d.active,
            max_concurrent_tasks=d.max_concurrent_tasks,
            permissions_profile_id=d.permissions_profile_id,
            heartbeat_at=d.heartbeat_at,
            current_task_id=d.current_task_id,
        )


class RunORM(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    initiated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> domain.Run:
        return domain.Run.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Run) -> "RunORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            mode=d.mode.value,
            status=d.status.value,
            started_at=d.started_at,
            ended_at=d.ended_at,
            initiated_by=d.initiated_by,
            resource_limits=d.resource_limits,
            summary=d.summary,
        )


class TaskRunORM(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    worktree_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sandbox_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    final_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> domain.TaskRun:
        return domain.TaskRun.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.TaskRun) -> "TaskRunORM":
        return cls(
            id=d.id,
            run_id=d.run_id,
            task_id=d.task_id,
            status=d.status.value,
            worktree_path=d.worktree_path,
            branch_name=d.branch_name,
            sandbox_id=d.sandbox_id,
            attempt_count=d.attempt_count,
            started_at=d.started_at,
            ended_at=d.ended_at,
            final_summary=d.final_summary,
        )


class HandoffORM(Base):
    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    from_role: Mapped[str] = mapped_column(String(50), nullable=False)
    to_role: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_domain(self) -> domain.Handoff:
        return domain.Handoff.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Handoff) -> "HandoffORM":
        return cls(
            id=d.id,
            task_run_id=d.task_run_id,
            from_role=d.from_role.value,
            to_role=d.to_role.value,
            kind=d.kind.value,
            payload_json=d.payload_json,
            priority=d.priority,
            status=d.status.value,
            created_at=d.created_at,
            consumed_at=d.consumed_at,
        )


class ArtifactORM(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.Artifact:
        return domain.Artifact.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Artifact) -> "ArtifactORM":
        return cls(
            id=d.id,
            task_run_id=d.task_run_id,
            type=d.type.value,
            path=d.path,
            content_hash=d.content_hash,
            summary=d.summary,
            created_at=d.created_at,
        )


class ModelRouteORM(Base):
    __tablename__ = "model_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="localforge", nullable=False)
    model_profile_id: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    fallback_model_profile_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.ModelRoute:
        return domain.ModelRoute(
            id=self.id,
            project_id=self.project_id,
            role=domain.AgentRole(self.role),
            provider=self.provider,
            model_profile_id=self.model_profile_id,
            endpoint_url=self.endpoint_url,
            fallback_model_profile_id=self.fallback_model_profile_id,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.ModelRoute) -> "ModelRouteORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            role=d.role.value,
            provider=d.provider,
            model_profile_id=d.model_profile_id,
            endpoint_url=d.endpoint_url,
            fallback_model_profile_id=d.fallback_model_profile_id,
            updated_at=d.updated_at,
        )


class ModelCallLedgerORM(Base):
    __tablename__ = "model_call_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="success", nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.ModelCallLedger:
        return domain.ModelCallLedger(
            id=self.id,
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=self.task_id,
            provider=self.provider,
            model=self.model,
            reason=domain.ChiefEngineerCallReason(self.reason),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            estimated_cost_usd=self.estimated_cost_usd,
            status=self.status,
            error_summary=self.error_summary,
            duration_ms=self.duration_ms,
            metadata=self.metadata_json,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.ModelCallLedger) -> "ModelCallLedgerORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            run_id=d.run_id,
            task_id=d.task_id,
            provider=d.provider,
            model=d.model,
            reason=d.reason.value,
            input_tokens=d.input_tokens,
            output_tokens=d.output_tokens,
            estimated_cost_usd=d.estimated_cost_usd,
            status=d.status,
            error_summary=d.error_summary,
            duration_ms=d.duration_ms,
            metadata_json=d.metadata,
            created_at=d.created_at,
        )


class MemoryFactORM(Base):
    __tablename__ = "memory_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), default="stack_fact", nullable=False)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="manual", nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.MemoryFact:
        return domain.MemoryFact(
            id=self.id,
            project_id=self.project_id,
            kind=domain.MemoryRecordKind(self.kind),
            fact=self.fact,
            source=self.source,
            pinned=self.pinned,
            status=self.status,
            tags=self.tags,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.MemoryFact) -> "MemoryFactORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            kind=d.kind.value,
            fact=d.fact,
            source=d.source,
            pinned=d.pinned,
            status=d.status,
            tags=d.tags,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class PolicyORM(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.Policy:
        return domain.Policy.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.Policy) -> "PolicyORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            name=d.name,
            rules=d.rules,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_redacted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.AuditEvent:
        return domain.AuditEvent.model_validate(self)

    @classmethod
    def from_domain(cls, d: domain.AuditEvent) -> "AuditEventORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            run_id=d.run_id,
            task_id=d.task_id,
            actor_type=d.actor_type.value,
            actor_id=d.actor_id,
            event_type=d.event_type.value,
            payload_redacted=d.payload_redacted,
            created_at=d.created_at,
        )


class ActionApprovalORM(Base):
    __tablename__ = "action_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    action_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def to_domain(self) -> domain.ActionApproval:
        return domain.ActionApproval(
            id=self.id,
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=self.task_id,
            action_kind=domain.ActionKind(self.action_kind),
            payload=self.payload_json,
            purpose=self.purpose,
            risk_level=self.risk_level,
            status=domain.ActionApprovalStatus(self.status),
            created_at=self.created_at,
            decided_at=self.decided_at,
            decided_by=self.decided_by,
        )

    @classmethod
    def from_domain(cls, d: domain.ActionApproval) -> "ActionApprovalORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            run_id=d.run_id,
            task_id=d.task_id,
            action_kind=d.action_kind.value,
            payload_json=d.payload,
            purpose=d.purpose,
            risk_level=d.risk_level,
            status=d.status.value,
            created_at=d.created_at,
            decided_at=d.decided_at,
            decided_by=d.decided_by,
        )


class TaskCommentORM(Base):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.TaskComment:
        return domain.TaskComment(
            id=self.id,
            project_id=self.project_id,
            task_id=self.task_id,
            author=self.author,
            body=self.body,
            thread_id=self.thread_id,
            metadata=self.metadata_json,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.TaskComment) -> "TaskCommentORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_id=d.task_id,
            author=d.author,
            body=d.body,
            thread_id=d.thread_id,
            metadata_json=d.metadata,
            created_at=d.created_at,
        )


class RuntimeRegistrationORM(Base):
    __tablename__ = "runtime_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    runtime_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), default="local", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ONLINE", nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.RuntimeRegistration:
        return domain.RuntimeRegistration(
            id=self.id,
            project_id=self.project_id,
            runtime_id=self.runtime_id,
            name=self.name,
            kind=self.kind,
            status=domain.RuntimeStatus(self.status),
            capabilities=self.capabilities,
            metadata=self.metadata_json,
            heartbeat_at=self.heartbeat_at,
            registered_at=self.registered_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.RuntimeRegistration) -> "RuntimeRegistrationORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            runtime_id=d.runtime_id,
            name=d.name,
            kind=d.kind,
            status=d.status.value,
            capabilities=d.capabilities,
            metadata_json=d.metadata,
            heartbeat_at=d.heartbeat_at,
            registered_at=d.registered_at,
            updated_at=d.updated_at,
        )


class SquadORM(Base):
    __tablename__ = "squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    agent_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.Squad:
        return domain.Squad(
            id=self.id,
            project_id=self.project_id,
            name=self.name,
            purpose=self.purpose,
            roles=[domain.AgentRole(role) for role in self.roles],
            agent_ids=self.agent_ids,
            metadata=self.metadata_json,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.Squad) -> "SquadORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            name=d.name,
            purpose=d.purpose,
            roles=[role.value for role in d.roles],
            agent_ids=d.agent_ids,
            metadata_json=d.metadata,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class PricingSourceORM(Base):
    __tablename__ = "pricing_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def to_domain(self) -> domain.PricingSource:
        return domain.PricingSource(
            id=self.id,
            provider=self.provider,
            url=self.url,
            retrieved_at=self.retrieved_at,
            notes=self.notes,
        )

    @classmethod
    def from_domain(cls, d: domain.PricingSource) -> "PricingSourceORM":
        return cls(
            id=d.id,
            provider=d.provider,
            url=d.url,
            retrieved_at=d.retrieved_at,
            notes=d.notes,
        )


class ModelPricingSnapshotORM(Base):
    __tablename__ = "model_pricing_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pricing_source_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_sources.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    input_price_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    output_price_per_million: Mapped[float] = mapped_column(Float, nullable=False)
    cached_input_price_per_million: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.ModelPricingSnapshot:
        return domain.ModelPricingSnapshot(
            id=self.id,
            pricing_source_id=self.pricing_source_id,
            model_name=self.model_name,
            input_price_per_million=self.input_price_per_million,
            output_price_per_million=self.output_price_per_million,
            cached_input_price_per_million=self.cached_input_price_per_million,
            is_manual=self.is_manual,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.ModelPricingSnapshot) -> "ModelPricingSnapshotORM":
        return cls(
            id=d.id,
            pricing_source_id=d.pricing_source_id,
            model_name=d.model_name,
            input_price_per_million=d.input_price_per_million,
            output_price_per_million=d.output_price_per_million,
            cached_input_price_per_million=d.cached_input_price_per_million,
            is_manual=d.is_manual,
            created_at=d.created_at,
        )


class ModelCapabilityORM(Base):
    __tablename__ = "model_capabilities"

    model_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_class: Mapped[str] = mapped_column(String(100), primary_key=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disqualified_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disqualification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    def to_domain(self) -> domain.ModelCapability:
        return domain.ModelCapability(
            model_name=self.model_name,
            task_class=self.task_class,
            success_count=self.success_count,
            failure_count=self.failure_count,
            disqualified_until=self.disqualified_until,
            disqualification_reason=self.disqualification_reason,
            metadata=self.metadata_json,
        )

    @classmethod
    def from_domain(cls, d: domain.ModelCapability) -> "ModelCapabilityORM":
        return cls(
            model_name=d.model_name,
            task_class=d.task_class,
            success_count=d.success_count,
            failure_count=d.failure_count,
            disqualified_until=d.disqualified_until,
            disqualification_reason=d.disqualification_reason,
            metadata_json=d.metadata,
        )


class LoopDefinitionORM(Base):
    __tablename__ = "loop_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="IDLE", nullable=False)
    trigger_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    detector: Mapped[str] = mapped_column(String(255), default="default_triage", nullable=False)
    execution_strategy: Mapped[str] = mapped_column(String(50), default="SEQUENTIAL", nullable=False)
    autonomy: Mapped[str] = mapped_column(String(50), default="L1_INSPECT", nullable=False)
    max_budget_usd: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    safety_policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    escalation_policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.LoopDefinition:
        return domain.LoopDefinition(
            id=self.id,
            project_id=self.project_id,
            name=self.name,
            repository_path=self.repository_path,
            enabled=self.enabled,
            status=enums.LoopStatus(self.status),
            trigger=domain.LoopTrigger.model_validate(self.trigger_json),
            detector=self.detector,
            execution_strategy=enums.ExecutionStrategy(self.execution_strategy),
            autonomy=enums.AutonomyLevel(self.autonomy),
            max_budget_usd=self.max_budget_usd,
            safety_policy=self.safety_policy_json,
            escalation_policy=self.escalation_policy_json,
            schema_version=self.schema_version,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.LoopDefinition) -> "LoopDefinitionORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            name=d.name,
            repository_path=d.repository_path,
            enabled=d.enabled,
            status=d.status.value if isinstance(d.status, enums.LoopStatus) else str(d.status),
            trigger_json=d.trigger.model_dump(),
            detector=d.detector,
            execution_strategy=d.execution_strategy.value if isinstance(d.execution_strategy, enums.ExecutionStrategy) else str(d.execution_strategy),
            autonomy=d.autonomy.value if isinstance(d.autonomy, enums.AutonomyLevel) else str(d.autonomy),
            max_budget_usd=d.max_budget_usd,
            safety_policy_json=d.safety_policy,
            escalation_policy_json=d.escalation_policy,
            schema_version=d.schema_version,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class LoopRunORM(Base):
    __tablename__ = "loop_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loop_id: Mapped[int] = mapped_column(
        ForeignKey("loop_definitions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    trigger_kind: Mapped[str] = mapped_column(String(50), default="MANUAL", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    triage_verdict: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    scheduler_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    items_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> domain.LoopRun:
        return domain.LoopRun(
            id=self.id,
            loop_id=self.loop_id,
            status=enums.LoopRunStatus(self.status),
            trigger_kind=enums.TriggerKind(self.trigger_kind),
            idempotency_key=self.idempotency_key,
            triage_verdict=enums.LoopRunVerdict(self.triage_verdict),
            scheduler_run_id=self.scheduler_run_id,
            items_processed=self.items_processed,
            cost_usd=self.cost_usd,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error_message=self.error_message,
        )

    @classmethod
    def from_domain(cls, d: domain.LoopRun) -> "LoopRunORM":
        return cls(
            id=d.id,
            loop_id=d.loop_id,
            status=d.status.value if isinstance(d.status, enums.LoopRunStatus) else str(d.status),
            trigger_kind=d.trigger_kind.value if isinstance(d.trigger_kind, enums.TriggerKind) else str(d.trigger_kind),
            idempotency_key=d.idempotency_key,
            triage_verdict=d.triage_verdict.value if isinstance(d.triage_verdict, enums.LoopRunVerdict) else str(d.triage_verdict),
            scheduler_run_id=d.scheduler_run_id,
            items_processed=d.items_processed,
            cost_usd=d.cost_usd,
            started_at=d.started_at,
            completed_at=d.completed_at,
            error_message=d.error_message,
        )



class LoopItemORM(Base):
    __tablename__ = "loop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loop_run_id: Mapped[int] = mapped_column(
        ForeignKey("loop_runs.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    scheduler_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.LoopItem:
        return domain.LoopItem(
            id=self.id,
            loop_run_id=self.loop_run_id,
            external_id=self.external_id,
            title=self.title,
            payload=self.payload_json,
            status=self.status,
            scheduler_task_id=self.scheduler_task_id,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.LoopItem) -> "LoopItemORM":
        return cls(
            id=d.id,
            loop_run_id=d.loop_run_id,
            external_id=d.external_id,
            title=d.title,
            payload_json=d.payload,
            status=d.status,
            scheduler_task_id=d.scheduler_task_id,
            idempotency_key=d.idempotency_key,
            created_at=d.created_at,
        )


class LoopStateSnapshotORM(Base):
    __tablename__ = "loop_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loop_id: Mapped[int] = mapped_column(
        ForeignKey("loop_definitions.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    active_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_eligible_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    circuit_status: Mapped[str] = mapped_column(String(50), default="CLOSED", nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    def to_domain(self) -> domain.LoopStateSnapshot:
        return domain.LoopStateSnapshot(
            id=self.id,
            loop_id=self.loop_id,
            snapshot_at=self.snapshot_at,
            active_run_id=self.active_run_id,
            last_run_at=self.last_run_at,
            next_eligible_run_at=self.next_eligible_run_at,
            circuit_status=self.circuit_status,
            total_runs=self.total_runs,
            total_cost_usd=self.total_cost_usd,
        )

    @classmethod
    def from_domain(cls, d: domain.LoopStateSnapshot) -> "LoopStateSnapshotORM":
        return cls(
            id=d.id,
            loop_id=d.loop_id,
            snapshot_at=d.snapshot_at,
            active_run_id=d.active_run_id,
            last_run_at=d.last_run_at,
            next_eligible_run_at=d.next_eligible_run_at,
            circuit_status=d.circuit_status,
            total_runs=d.total_runs,
            total_cost_usd=d.total_cost_usd,
        )


class CircuitBreakerStateORM(Base):
    __tablename__ = "circuit_breaker_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="CLOSED", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stagnation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fingerprint_counts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.CircuitBreakerState:
        return domain.CircuitBreakerState(
            id=self.id,
            project_id=self.project_id,
            scope=enums.CircuitScope(self.scope),
            target_id=self.target_id,
            state=enums.CircuitState(self.state),
            consecutive_failures=self.consecutive_failures,
            stagnation_count=self.stagnation_count,
            fingerprint_counts=self.fingerprint_counts_json,
            last_fingerprint=self.last_fingerprint,
            opened_at=self.opened_at,
            cooldown_until=self.cooldown_until,
            reason=self.reason,
            evidence_json=self.evidence_json,
            schema_version=self.schema_version,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.CircuitBreakerState) -> "CircuitBreakerStateORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            scope=d.scope.value if isinstance(d.scope, enums.CircuitScope) else str(d.scope),
            target_id=d.target_id,
            state=d.state.value if isinstance(d.state, enums.CircuitState) else str(d.state),
            consecutive_failures=d.consecutive_failures,
            stagnation_count=d.stagnation_count,
            fingerprint_counts_json=d.fingerprint_counts,
            last_fingerprint=d.last_fingerprint,
            opened_at=d.opened_at,
            cooldown_until=d.cooldown_until,
            reason=d.reason,
            evidence_json=d.evidence_json,
            schema_version=d.schema_version,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class MakerCheckerVerificationORM(Base):
    __tablename__ = "maker_checker_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    maker_agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    checker_agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    tests_executed_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    not_checked_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)

    deterministic_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checker_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.MakerCheckerVerification:
        return domain.MakerCheckerVerification(
            id=self.id,
            project_id=self.project_id,
            task_run_id=self.task_run_id,
            maker_agent_id=self.maker_agent_id,
            checker_agent_id=self.checker_agent_id,
            status=enums.VerificationStatus(self.status),
            tests_executed=self.tests_executed_json if isinstance(self.tests_executed_json, list) else [],
            not_checked=self.not_checked_json if isinstance(self.not_checked_json, list) else [],
            deterministic_passed=self.deterministic_passed,
            checker_feedback=self.checker_feedback,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.MakerCheckerVerification) -> "MakerCheckerVerificationORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_run_id=d.task_run_id,
            maker_agent_id=d.maker_agent_id,
            checker_agent_id=d.checker_agent_id,
            status=d.status.value if isinstance(d.status, enums.VerificationStatus) else str(d.status),
            tests_executed_json=d.tests_executed,
            not_checked_json=d.not_checked,
            deterministic_passed=d.deterministic_passed,
            checker_feedback=d.checker_feedback,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class WorktreeAttemptManifestORM(Base):
    __tablename__ = "worktree_attempt_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    worktree_path: Mapped[str] = mapped_column(Text, nullable=False)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_commit: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_paths_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    leases_held_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.WorktreeAttemptManifest:
        return domain.WorktreeAttemptManifest(
            id=self.id,
            project_id=self.project_id,
            task_id=self.task_id,
            task_run_id=self.task_run_id,
            attempt_number=self.attempt_number,
            worktree_path=self.worktree_path,
            branch_name=self.branch_name,
            source_commit=self.source_commit,
            owner_agent_id=self.owner_agent_id,
            expected_paths=self.expected_paths_json if isinstance(self.expected_paths_json, list) else [],
            leases_held=self.leases_held_json if isinstance(self.leases_held_json, list) else [],
            status=enums.WorktreeAttemptStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.WorktreeAttemptManifest) -> "WorktreeAttemptManifestORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_id=d.task_id,
            task_run_id=d.task_run_id,
            attempt_number=d.attempt_number,
            worktree_path=d.worktree_path,
            branch_name=d.branch_name,
            source_commit=d.source_commit,
            owner_agent_id=d.owner_agent_id,
            expected_paths_json=d.expected_paths,
            leases_held_json=d.leases_held,
            status=d.status.value if isinstance(d.status, enums.WorktreeAttemptStatus) else str(d.status),
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class PathLeaseORM(Base):
    __tablename__ = "path_leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_directory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    release_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.PathLease:
        return domain.PathLease(
            id=self.id,
            project_id=self.project_id,
            task_run_id=self.task_run_id,
            owner_id=self.owner_id,
            target_path=self.target_path,
            is_directory=self.is_directory,
            ttl_seconds=self.ttl_seconds,
            expires_at=self.expires_at,
            release_reason=enums.LeaseReleaseReason(self.release_reason) if self.release_reason else None,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.PathLease) -> "PathLeaseORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_run_id=d.task_run_id,
            owner_id=d.owner_id,
            target_path=d.target_path,
            is_directory=d.is_directory,
            ttl_seconds=d.ttl_seconds,
            expires_at=d.expires_at,
            release_reason=d.release_reason.value if isinstance(d.release_reason, enums.LeaseReleaseReason) else d.release_reason,
            created_at=d.created_at,
        )


class RunnerPoolStateORM(Base):
    __tablename__ = "runner_pool_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runner_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lane: Mapped[str] = mapped_column(String(50), default="INLINE", nullable=False)
    health_state: Mapped[str] = mapped_column(String(50), default="READY", nullable=False)
    active_tasks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    capabilities_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.RunnerPoolState:
        caps_dict = self.capabilities_json if isinstance(self.capabilities_json, dict) else {}
        return domain.RunnerPoolState(
            id=self.id,
            runner_id=self.runner_id,
            name=self.name,
            lane=enums.RunnerLane(self.lane),
            health_state=enums.RunnerHealthState(self.health_state),
            active_tasks_count=self.active_tasks_count,
            max_concurrency=self.max_concurrency,
            capabilities=domain.RunnerCapability.model_validate(caps_dict) if caps_dict else domain.RunnerCapability(),
            success_rate=self.success_rate,
            quarantine_reason=self.quarantine_reason,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.RunnerPoolState) -> "RunnerPoolStateORM":
        return cls(
            id=d.id,
            runner_id=d.runner_id,
            name=d.name,
            lane=d.lane.value if isinstance(d.lane, enums.RunnerLane) else str(d.lane),
            health_state=d.health_state.value if isinstance(d.health_state, enums.RunnerHealthState) else str(d.health_state),
            active_tasks_count=d.active_tasks_count,
            max_concurrency=d.max_concurrency,
            capabilities_json=d.capabilities.model_dump(mode="json"),
            success_rate=d.success_rate,
            quarantine_reason=d.quarantine_reason,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class RunnerDispatchLogORM(Base):
    __tablename__ = "runner_dispatch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    selected_runner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_status: Mapped[str] = mapped_column(String(50), default="SUCCESS", nullable=False)
    ranking_scores_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    rejection_reasons_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.RunnerDispatchLog:
        return domain.RunnerDispatchLog(
            id=self.id,
            project_id=self.project_id,
            task_run_id=self.task_run_id,
            selected_runner_id=self.selected_runner_id,
            dispatch_status=self.dispatch_status,
            ranking_scores_json=self.ranking_scores_json if isinstance(self.ranking_scores_json, dict) else {},
            rejection_reasons_json=self.rejection_reasons_json if isinstance(self.rejection_reasons_json, dict) else {},
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.RunnerDispatchLog) -> "RunnerDispatchLogORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_run_id=d.task_run_id,
            selected_runner_id=d.selected_runner_id,
            dispatch_status=d.dispatch_status,
            ranking_scores_json=d.ranking_scores_json,
            rejection_reasons_json=d.rejection_reasons_json,
            created_at=d.created_at,
        )


class TypedHandoffArtifactORM(Base):
    __tablename__ = "typed_handoff_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    producer_agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    consumer_agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), default="RESEARCH", nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    changed_files_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    tests_executed_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    validation_results_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    open_questions_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    risks_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    not_checked_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.TypedHandoffArtifact:
        return domain.TypedHandoffArtifact(
            id=self.id,
            project_id=self.project_id,
            task_run_id=self.task_run_id,
            producer_agent_id=self.producer_agent_id,
            consumer_agent_id=self.consumer_agent_id,
            artifact_type=enums.TypedArtifactType(self.artifact_type),
            schema_version=self.schema_version,
            summary=self.summary,
            evidence_json=self.evidence_json if isinstance(self.evidence_json, dict) else {},
            changed_files=self.changed_files_json if isinstance(self.changed_files_json, list) else [],
            tests_executed=self.tests_executed_json if isinstance(self.tests_executed_json, list) else [],
            validation_results_json=self.validation_results_json if isinstance(self.validation_results_json, dict) else {},
            open_questions=self.open_questions_json if isinstance(self.open_questions_json, list) else [],
            risks=self.risks_json if isinstance(self.risks_json, list) else [],
            not_checked=self.not_checked_json if isinstance(self.not_checked_json, list) else [],
            content_hash=self.content_hash,
            is_consumed=self.is_consumed,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.TypedHandoffArtifact) -> "TypedHandoffArtifactORM":
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_run_id=d.task_run_id,
            producer_agent_id=d.producer_agent_id,
            consumer_agent_id=d.consumer_agent_id,
            artifact_type=d.artifact_type.value if isinstance(d.artifact_type, enums.TypedArtifactType) else str(d.artifact_type),
            schema_version=d.schema_version,
            summary=d.summary,
            evidence_json=d.evidence_json,
            changed_files_json=d.changed_files,
            tests_executed_json=d.tests_executed,
            validation_results_json=d.validation_results_json,
            open_questions_json=d.open_questions,
            risks_json=d.risks,
            not_checked_json=d.not_checked,
            content_hash=d.content_hash,
            is_consumed=d.is_consumed,
            created_at=d.created_at,
        )


class SwarmPlanORM(Base):
    """ORM for SwarmPlan — the server-owned validated DAG plan for a Light Swarm."""

    __tablename__ = "swarm_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False, default="LIGHT")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    nodes_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    edges_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_domain(self) -> domain.SwarmPlan:
        from localforge.models.enums import SwarmStrategy, SwarmStatus, SwarmNodeType, SwarmNodeStatus, TypedArtifactType
        from localforge.models.domain import SwarmNode, SwarmPolicy

        nodes = [SwarmNode(**n) for n in (self.nodes_json or [])]
        edges: list[tuple[str, str]] = [tuple(e) for e in (self.edges_json or [])]  # type: ignore[misc]
        policy = SwarmPolicy(**self.policy_json) if self.policy_json else SwarmPolicy()
        return domain.SwarmPlan(
            id=self.id,
            project_id=self.project_id,
            task_run_id=self.task_run_id,
            strategy=SwarmStrategy(self.strategy),
            status=SwarmStatus(self.status),
            policy=policy,
            nodes=nodes,
            edges=edges,
            paused_at=self.paused_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, d: domain.SwarmPlan) -> "SwarmPlanORM":
        nodes_json = [n.model_dump(mode="json") for n in d.nodes]
        edges_json = [list(e) for e in d.edges]
        return cls(
            id=d.id,
            project_id=d.project_id,
            task_run_id=d.task_run_id,
            strategy=d.strategy.value if isinstance(d.strategy, enums.SwarmStrategy) else str(d.strategy),
            status=d.status.value if isinstance(d.status, enums.SwarmStatus) else str(d.status),
            policy_json=d.policy.model_dump(mode="json"),
            nodes_json=nodes_json,
            edges_json=edges_json,
            paused_at=d.paused_at,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class SwarmRunORM(Base):
    """ORM for SwarmRun — mutable execution state of a swarm."""

    __tablename__ = "swarm_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("swarm_plans.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    active_node_ids_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    cumulative_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cumulative_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    node_statuses_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verdict: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    def to_domain(self) -> domain.SwarmRun:
        from localforge.models.enums import SwarmStatus
        return domain.SwarmRun(
            id=self.id,
            plan_id=self.plan_id,
            status=SwarmStatus(self.status),
            active_node_ids=list(self.active_node_ids_json or []),
            cumulative_cost_usd=self.cumulative_cost_usd,
            cumulative_tokens=self.cumulative_tokens,
            node_statuses=dict(self.node_statuses_json or {}),
            verdict=self.verdict,
            started_at=self.started_at,
            finished_at=self.finished_at,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, d: domain.SwarmRun) -> "SwarmRunORM":
        return cls(
            id=d.id,
            plan_id=d.plan_id,
            status=d.status.value if isinstance(d.status, enums.SwarmStatus) else str(d.status),
            active_node_ids_json=list(d.active_node_ids),
            cumulative_cost_usd=d.cumulative_cost_usd,
            cumulative_tokens=d.cumulative_tokens,
            node_statuses_json=dict(d.node_statuses),
            verdict=d.verdict,
            started_at=d.started_at,
            finished_at=d.finished_at,
            created_at=d.created_at,
        )

