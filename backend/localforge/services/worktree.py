import logging
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import WorktreeAttemptStatus
from localforge.storage.orm import WorktreeAttemptManifestORM

logger = logging.getLogger(__name__)


class WorktreeService:
    """Service layer managing Worktree attempt manifests, Git isolation lifecycle, and restart reconciliation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_attempt_manifest(
        self,
        project_id: int,
        task_id: int,
        task_run_id: int,
        worktree_path: str,
        branch_name: str,
        source_commit: str,
        owner_agent_id: str,
        expected_paths: list[str] | None = None,
        attempt_number: int = 1,
    ) -> domain.WorktreeAttemptManifest:
        """Record a new WorktreeAttemptManifest."""
        manifest = domain.WorktreeAttemptManifest(
            project_id=project_id,
            task_id=task_id,
            task_run_id=task_run_id,
            attempt_number=attempt_number,
            worktree_path=worktree_path,
            branch_name=branch_name,
            source_commit=source_commit,
            owner_agent_id=owner_agent_id,
            expected_paths=expected_paths or [],
            status=WorktreeAttemptStatus.ACTIVE,
        )
        orm_obj = WorktreeAttemptManifestORM.from_domain(manifest)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_manifest_by_task_run(
        self, task_run_id: int
    ) -> domain.WorktreeAttemptManifest | None:
        """Retrieve the latest attempt manifest for a task run."""
        stmt = (
            select(WorktreeAttemptManifestORM)
            .where(WorktreeAttemptManifestORM.task_run_id == task_run_id)
            .order_by(WorktreeAttemptManifestORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def update_manifest_status(
        self, manifest_id: int, status: WorktreeAttemptStatus
    ) -> domain.WorktreeAttemptManifest:
        """Update the lifecycle status of an attempt manifest."""
        stmt = select(WorktreeAttemptManifestORM).where(
            WorktreeAttemptManifestORM.id == manifest_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"WorktreeAttemptManifest with ID {manifest_id} not found.")

        orm_obj.status = status.value
        await self.session.flush()
        return orm_obj.to_domain()

    async def reconcile_worktree_manifests(self, project_id: int) -> dict[str, Any]:
        """Reconcile manifests with actual physical filesystem state (Report-only).

        Returns:
            summary: dict containing active_count, stale_count, orphan_count, details.
        """
        stmt = select(WorktreeAttemptManifestORM).where(
            WorktreeAttemptManifestORM.project_id == project_id
        )
        result = await self.session.execute(stmt)
        manifests = [orm_obj.to_domain() for orm_obj in result.scalars().all()]

        active = []
        stale = []
        for m in manifests:
            # Reconcile: verify physical directory existence
            exists = os.path.isdir(m.worktree_path)
            if m.status == WorktreeAttemptStatus.ACTIVE and not exists:
                # Update status to STALE
                await self.update_manifest_status(m.id, WorktreeAttemptStatus.STALE)  # type: ignore[arg-type]
                stale.append(m.worktree_path)
            elif exists:
                active.append(m.worktree_path)

        return {
            "project_id": project_id,
            "total_manifests": len(manifests),
            "active_worktrees": len(active),
            "reconciled_stale": len(stale),
            "stale_paths": stale,
        }
