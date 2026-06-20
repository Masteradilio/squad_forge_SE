from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from localforge.models import domain


class Base(DeclarativeBase):
    pass


class SchemaVersionORM(Base):
    __tablename__ = "schema_versions"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False)
    remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    localforge_config_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
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
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
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
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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


class PolicyORM(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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

