from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.services.security_controls import redact_secrets_recursive
from localforge.storage.orm import ArtifactORM, AuditEventORM, PolicyORM


class AuditService:
    """Service layer managing immutable Audit Events, Artifacts, and Policies."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # Audit Event Operations (Append-only)
    async def append_audit_event(self, event: domain.AuditEvent) -> domain.AuditEvent:
        """Append a new audit event.

        This service enforces that audit events are append-only.
        """
        event.payload_redacted = cast(
            dict[str, Any],
            redact_secrets_recursive(event.payload_redacted),
        )
        orm_obj = AuditEventORM.from_domain(event)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_audit_event(self, event_id: int) -> domain.AuditEvent | None:
        """Retrieve an audit event by ID."""
        result = await self.session.execute(
            select(AuditEventORM).where(AuditEventORM.id == event_id)
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_audit_events_for_project(self, project_id: int) -> list[domain.AuditEvent]:
        """Retrieve all audit events for a project."""
        result = await self.session.execute(
            select(AuditEventORM)
            .where(AuditEventORM.project_id == project_id)
            .order_by(AuditEventORM.created_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    # Artifact Operations
    async def create_artifact(self, artifact: domain.Artifact) -> domain.Artifact:
        """Create a new artifact record."""
        orm_obj = ArtifactORM.from_domain(artifact)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_artifact(self, artifact_id: int) -> domain.Artifact | None:
        """Retrieve an artifact by ID."""
        result = await self.session.execute(
            select(ArtifactORM).where(ArtifactORM.id == artifact_id)
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_artifacts_for_task_run(self, task_run_id: int) -> list[domain.Artifact]:
        """List all artifacts generated during a specific task run."""
        result = await self.session.execute(
            select(ArtifactORM)
            .where(ArtifactORM.task_run_id == task_run_id)
            .order_by(ArtifactORM.created_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def list_artifacts_for_task_runs(
        self, task_run_ids: list[int]
    ) -> dict[int, list[domain.Artifact]]:
        """List artifacts for several task runs using a single query."""
        if not task_run_ids:
            return {}
        result = await self.session.execute(
            select(ArtifactORM)
            .where(ArtifactORM.task_run_id.in_(task_run_ids))
            .order_by(ArtifactORM.task_run_id, ArtifactORM.created_at.desc())
        )
        artifacts_by_task_run: dict[int, list[domain.Artifact]] = {}
        for orm_obj in result.scalars().all():
            artifacts_by_task_run.setdefault(orm_obj.task_run_id, []).append(orm_obj.to_domain())
        return artifacts_by_task_run

    # Policy Operations
    async def create_policy(self, policy: domain.Policy) -> domain.Policy:
        """Create a new policy."""
        orm_obj = PolicyORM.from_domain(policy)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_policy(self, policy_id: int) -> domain.Policy | None:
        """Retrieve a policy by ID."""
        result = await self.session.execute(select(PolicyORM).where(PolicyORM.id == policy_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_project_policy(self, project_id: int, name: str) -> domain.Policy | None:
        """Retrieve a policy by name for a specific project."""
        result = await self.session.execute(
            select(PolicyORM).where(PolicyORM.project_id == project_id, PolicyORM.name == name)
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def update_policy(self, policy: domain.Policy) -> domain.Policy:
        """Update the rules of an existing policy."""
        if not policy.id:
            raise ValueError("Cannot update a policy without an ID")

        result = await self.session.execute(select(PolicyORM).where(PolicyORM.id == policy.id))
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Policy with ID {policy.id} not found")

        orm_obj.name = policy.name
        orm_obj.rules = policy.rules
        orm_obj.updated_at = policy.updated_at

        await self.session.flush()
        return orm_obj.to_domain()

    async def export_run_replay(
        self,
        project_id: int,
        run_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Export the chronological timeline of events and artifacts for a specific run.

        Ensures all secrets are redacted in the exported JSON-serializable list.
        """
        # 1. Fetch all audit events sorted chronologically with pagination
        events_result = await self.session.execute(
            select(AuditEventORM)
            .where(
                AuditEventORM.project_id == project_id,
                AuditEventORM.run_id == run_id,
            )
            .order_by(AuditEventORM.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        events = events_result.scalars().all()

        # 2. Fetch all artifacts associated with task runs belonging to this run_id
        from localforge.storage.orm import TaskRunORM

        task_runs_result = await self.session.execute(
            select(TaskRunORM.id).where(TaskRunORM.run_id == run_id)
        )
        task_run_ids = [r[0] for r in task_runs_result.all()]

        artifacts_by_task_run = await self.list_artifacts_for_task_runs(task_run_ids)
        task_run_ids_by_task: dict[int, list[int]] = {}
        if task_run_ids:
            task_runs_for_map = await self.session.execute(
                select(TaskRunORM.id, TaskRunORM.task_id).where(TaskRunORM.run_id == run_id)
            )
            for tr_id, task_id in task_runs_for_map.all():
                task_run_ids_by_task.setdefault(task_id, []).append(tr_id)

        # 3. Build chronological timeline
        timeline: list[dict[str, Any]] = []
        for event_orm in events:
            event = event_orm.to_domain()
            # Redact event payload before exporting (as double-safety check)
            event.payload_redacted = cast(
                dict[str, Any],
                redact_secrets_recursive(event.payload_redacted),
            )

            artifacts_list: list[dict[str, Any]] = []

            event_data: dict[str, Any] = {
                "id": event.id,
                "timestamp": event.created_at.isoformat(),
                "actor_type": event.actor_type.value,
                "actor_id": event.actor_id,
                "event_type": event.event_type.value,
                "payload": event.payload_redacted,
                "artifacts": artifacts_list,
            }

            # If the event is bound to a task, include artifacts for its task run
            if event.task_id and task_run_ids_by_task:
                for tr_id in task_run_ids_by_task.get(event.task_id, []):
                    if tr_id in artifacts_by_task_run:
                        for art in artifacts_by_task_run[tr_id]:
                            artifacts_list.append(
                                {
                                    "id": art.id,
                                    "type": art.type.value,
                                    "path": art.path,
                                    "content_hash": art.content_hash,
                                    "summary": art.summary,
                                }
                            )

            timeline.append(event_data)

        return timeline
