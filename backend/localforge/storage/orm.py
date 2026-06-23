from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from localforge.models import domain


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
