import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import LeaseReleaseReason
from localforge.storage.orm import PathLeaseORM

logger = logging.getLogger(__name__)


def is_path_overlapping(path_a: str, path_b: str) -> bool:
    """Check if two paths overlap (exact match or parent-child hierarchy relationship)."""
    norm_a = os.path.normcase(os.path.normpath(path_a)).replace("\\", "/")
    norm_b = os.path.normcase(os.path.normpath(path_b)).replace("\\", "/")

    if norm_a == norm_b:
        return True

    # Check parent-child hierarchy
    if not norm_a.endswith("/"):
        norm_a_dir = norm_a + "/"
    else:
        norm_a_dir = norm_a

    if not norm_b.endswith("/"):
        norm_b_dir = norm_b + "/"
    else:
        norm_b_dir = norm_b

    return norm_b.startswith(norm_a_dir) or norm_a.startswith(norm_b_dir)


class PathLeaseService:
    """Service layer managing PathIntent write leases, overlap detection, TTLs, and deadlock resolution."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def acquire_lease(
        self,
        project_id: int,
        task_run_id: int,
        owner_id: str,
        target_path: str,
        is_directory: bool = False,
        ttl_seconds: int = 3600,
    ) -> tuple[domain.PathLease | None, str | None, str]:
        """Attempt to acquire an exclusive write lease for a target path.

        Returns:
            (lease: PathLease | None, conflict_owner_id: str | None, message: str)
        """
        now = datetime.now(UTC)
        # Fetch active, unexpired leases for the same project
        stmt = select(PathLeaseORM).where(
            PathLeaseORM.project_id == project_id,
            PathLeaseORM.release_reason.is_(None),
            PathLeaseORM.expires_at > now,
        )
        result = await self.session.execute(stmt)
        active_leases = [orm_obj.to_domain() for orm_obj in result.scalars().all()]

        # Check overlap against active leases held by OTHER owners
        for lease in active_leases:
            if lease.owner_id != owner_id and is_path_overlapping(lease.target_path, target_path):
                msg = f"PathIntent conflict: target '{target_path}' overlaps with active lease on '{lease.target_path}' held by '{lease.owner_id}'."
                logger.warning(msg)
                return None, lease.owner_id, msg

        # Acquire lease
        expires_at = now + timedelta(seconds=ttl_seconds)
        lease_domain = domain.PathLease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id=owner_id,
            target_path=target_path,
            is_directory=is_directory,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )
        orm_obj = PathLeaseORM.from_domain(lease_domain)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain(), None, f"Lease acquired for '{target_path}'."

    async def release_lease(
        self, lease_id: int, reason: LeaseReleaseReason
    ) -> domain.PathLease | None:
        """Release a specific path lease."""
        stmt = select(PathLeaseORM).where(PathLeaseORM.id == lease_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            return None

        orm_obj.release_reason = reason.value
        await self.session.flush()
        return orm_obj.to_domain()

    async def release_all_leases_for_run(self, task_run_id: int, reason: LeaseReleaseReason) -> int:
        """Release all active path leases associated with a task run (e.g. on completion or cancellation)."""
        stmt = select(PathLeaseORM).where(
            PathLeaseORM.task_run_id == task_run_id,
            PathLeaseORM.release_reason.is_(None),
        )
        result = await self.session.execute(stmt)
        leases = result.scalars().all()

        count = 0
        for lease in leases:
            lease.release_reason = reason.value
            count += 1

        await self.session.flush()
        return count

    async def list_active_leases(self, project_id: int) -> list[domain.PathLease]:
        """List all active unexpired leases for a project."""
        now = datetime.now(UTC)
        stmt = select(PathLeaseORM).where(
            PathLeaseORM.project_id == project_id,
            PathLeaseORM.release_reason.is_(None),
            PathLeaseORM.expires_at > now,
        )
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]
