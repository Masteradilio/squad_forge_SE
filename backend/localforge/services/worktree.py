import logging
import os
import subprocess
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import WorktreeAttemptStatus
from localforge.storage.orm import ProjectORM, WorktreeAttemptManifestORM

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

    async def validate_repository_state(self, manifest_id: int) -> dict[str, Any]:
        """Validate worktree cleanliness and target-branch drift for a manifest."""
        stmt = (
            select(WorktreeAttemptManifestORM, ProjectORM)
            .join(ProjectORM, ProjectORM.id == WorktreeAttemptManifestORM.project_id)
            .where(WorktreeAttemptManifestORM.id == manifest_id)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise ValueError(f"WorktreeAttemptManifest with ID {manifest_id} not found.")

        manifest, project = row
        if not os.path.isdir(manifest.worktree_path):
            manifest.status = WorktreeAttemptStatus.STALE.value
            await self.session.flush()
            return {
                "manifest_id": manifest.id,
                "status": WorktreeAttemptStatus.STALE.value,
                "worktree_exists": False,
                "clean": False,
                "target_drift": True,
                "reason": "Worktree path is missing on disk.",
            }

        porcelain = self._run_git(manifest.worktree_path, ["status", "--porcelain"])
        head_commit = self._run_git(manifest.worktree_path, ["rev-parse", "HEAD"]).strip()
        target_commit = self._run_git(
            manifest.worktree_path, ["rev-parse", project.default_branch]
        ).strip()
        clean = porcelain.strip() == ""
        target_drift = target_commit != manifest.source_commit
        if not clean or target_drift:
            manifest.status = WorktreeAttemptStatus.REJECTED.value
        await self.session.flush()
        return {
            "manifest_id": manifest.id,
            "status": manifest.status,
            "worktree_exists": True,
            "clean": clean,
            "target_drift": target_drift,
            "head_commit": head_commit,
            "source_commit": manifest.source_commit,
            "target_commit": target_commit,
            "default_branch": project.default_branch,
            "dirty_paths": porcelain.splitlines(),
        }

    def _run_git(self, worktree_path: str, args: list[str]) -> str:
        result = subprocess.run(
            ["git", "-C", worktree_path, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Git worktree validation failed: "
                f"git -C {worktree_path} {' '.join(args)}\n{result.stderr.strip()}"
            )
        return result.stdout

    async def cancel_manifests_for_task_run(self, task_run_id: int) -> int:
        """Mark active worktree attempt manifests for a task run as cancelled."""
        stmt = select(WorktreeAttemptManifestORM).where(
            WorktreeAttemptManifestORM.task_run_id == task_run_id,
            WorktreeAttemptManifestORM.status == WorktreeAttemptStatus.ACTIVE.value,
        )
        result = await self.session.execute(stmt)
        manifests = result.scalars().all()
        for manifest in manifests:
            manifest.status = WorktreeAttemptStatus.CANCELLED.value
        await self.session.flush()
        return len(manifests)

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
