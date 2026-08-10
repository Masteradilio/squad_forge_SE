from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import ArtifactType, RuntimeStatus
from localforge.storage.orm import (
    ArtifactORM,
    EpicORM,
    ProductDocumentORM,
    RuntimeRegistrationORM,
    ProjectORM,
    SquadORM,
    TaskCommentORM,
    TaskORM,
    TaskRunORM,
)
from localforge.services.tenant_context import session_tenant


class CoordinationService:
    """Control-plane helpers for comments, runtimes, and traceability."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _tenant_id(self) -> str:
        return session_tenant(self.session)

    async def add_task_comment(self, comment: domain.TaskComment) -> domain.TaskComment:
        task = await self.session.execute(
            select(TaskORM.id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskORM.id == comment.task_id, ProjectORM.tenant_id == self._tenant_id())
        )
        if task.scalar_one_or_none() is None:
            raise ValueError("Task comment target is not accessible in the current tenant")
        orm_obj = TaskCommentORM.from_domain(comment)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_task_comments(self, task_id: int, limit: int = 50) -> list[domain.TaskComment]:
        result = await self.session.execute(
            select(TaskCommentORM)
            .join(TaskORM, TaskORM.id == TaskCommentORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskCommentORM.task_id == task_id, ProjectORM.tenant_id == self._tenant_id())
            .order_by(TaskCommentORM.created_at.desc(), TaskCommentORM.id.desc())
            .limit(limit)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def recent_comments_for_context(
        self, task_id: int, limit: int = 10
    ) -> list[domain.TaskComment]:
        return await self.list_task_comments(task_id=task_id, limit=limit)

    async def register_runtime(
        self, runtime: domain.RuntimeRegistration
    ) -> domain.RuntimeRegistration:
        result = await self.session.execute(
            select(RuntimeRegistrationORM)
            .join(ProjectORM, ProjectORM.id == RuntimeRegistrationORM.project_id)
            .where(
                RuntimeRegistrationORM.runtime_id == runtime.runtime_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.name = runtime.name
            existing.kind = runtime.kind
            existing.status = runtime.status.value
            existing.capabilities = runtime.capabilities
            existing.metadata_json = runtime.metadata
            existing.heartbeat_at = runtime.heartbeat_at
            existing.updated_at = datetime.now(UTC)
            await self.session.flush()
            return existing.to_domain()

        orm_obj = RuntimeRegistrationORM.from_domain(runtime)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def heartbeat_runtime(
        self,
        runtime_id: str,
        status: RuntimeStatus = RuntimeStatus.ONLINE,
        metadata: dict[str, Any] | None = None,
    ) -> domain.RuntimeRegistration | None:
        result = await self.session.execute(
            select(RuntimeRegistrationORM)
            .join(ProjectORM, ProjectORM.id == RuntimeRegistrationORM.project_id)
            .where(
                RuntimeRegistrationORM.runtime_id == runtime_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        runtime = result.scalar_one_or_none()
        if not runtime:
            return None
        runtime.status = status.value
        runtime.heartbeat_at = datetime.now(UTC)
        runtime.updated_at = datetime.now(UTC)
        if metadata is not None:
            runtime.metadata_json = metadata
        await self.session.flush()
        return runtime.to_domain()

    async def list_runtimes(self, project_id: int) -> list[domain.RuntimeRegistration]:
        result = await self.session.execute(
            select(RuntimeRegistrationORM)
            .join(ProjectORM, ProjectORM.id == RuntimeRegistrationORM.project_id)
            .where(RuntimeRegistrationORM.project_id == project_id, ProjectORM.tenant_id == self._tenant_id())
            .order_by(RuntimeRegistrationORM.updated_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def task_ancestry(self, task_id: int) -> dict[str, Any]:
        task_result = await self.session.execute(
            select(TaskORM)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskORM.id == task_id, ProjectORM.tenant_id == self._tenant_id())
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            raise ValueError(f"Task with ID {task_id} not found")

        epic = await self.session.get(EpicORM, task.epic_id) if task.epic_id else None
        document = (
            await self.session.get(ProductDocumentORM, epic.source_document_id)
            if epic and epic.source_document_id
            else None
        )
        run_result = await self.session.execute(
            select(TaskRunORM)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskRunORM.task_id == task_id, ProjectORM.tenant_id == self._tenant_id())
            .order_by(TaskRunORM.started_at.desc())
        )
        task_runs = list(run_result.scalars().all())
        artifacts_by_task_run: dict[int, list[dict[str, Any]]] = {}
        pr_artifacts: list[dict[str, Any]] = []
        task_run_ids = [tr.id for tr in task_runs]
        if task_run_ids:
            artifact_result = await self.session.execute(
                select(ArtifactORM)
                .join(TaskRunORM, TaskRunORM.id == ArtifactORM.task_run_id)
                .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
                .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
                .where(ArtifactORM.task_run_id.in_(task_run_ids), ProjectORM.tenant_id == self._tenant_id())
                .order_by(ArtifactORM.created_at.desc())
            )
            for artifact in artifact_result.scalars().all():
                artifact_data = artifact.to_domain().model_dump(mode="json")
                artifacts_by_task_run.setdefault(artifact.task_run_id, []).append(artifact_data)
                if artifact.type == ArtifactType.PR.value:
                    pr_artifacts.append(artifact_data)

        return {
            "document": document.to_domain().model_dump(mode="json") if document else None,
            "epic": epic.to_domain().model_dump(mode="json") if epic else None,
            "task": task.to_domain().model_dump(mode="json"),
            "task_runs": [
                {
                    **task_run.to_domain().model_dump(mode="json"),
                    "artifacts": artifacts_by_task_run.get(task_run.id, []),
                }
                for task_run in task_runs
            ],
            "pr_artifacts": pr_artifacts,
        }

    async def create_squad(self, squad: domain.Squad) -> domain.Squad:
        orm_obj = SquadORM.from_domain(squad)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_squads(self, project_id: int) -> list[domain.Squad]:
        result = await self.session.execute(
            select(SquadORM).where(SquadORM.project_id == project_id).order_by(SquadORM.name)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]
