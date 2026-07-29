import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import LeaseReleaseReason
from localforge.storage.orm import PathLeaseORM

logger = logging.getLogger(__name__)


def normalize_lease_path(path: str) -> str:
    """Normalize a lease path into a comparable repository-relative form."""
    normalized = os.path.normpath(path).replace("\\", "/").strip("/")
    normalized = str(PurePosixPath(normalized))
    if os.name == "nt":
        normalized = normalized.lower()
    return normalized


def is_path_overlapping(path_a: str, path_b: str) -> bool:
    """Check if two paths overlap (exact match or parent-child hierarchy relationship)."""
    norm_a = normalize_lease_path(path_a)
    norm_b = normalize_lease_path(path_b)

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
        attempt_number: int = 1,
        worktree_path: str | None = None,
        fencing_token: str | None = None,
    ) -> tuple[domain.PathLease | None, str | None, str]:
        """Attempt to acquire an exclusive write lease for a target path.

        Returns:
            (lease: PathLease | None, conflict_owner_id: str | None, message: str)
        """
        now = datetime.now(UTC)
        normalized_target_path = normalize_lease_path(target_path)
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
            if lease.owner_id != owner_id and is_path_overlapping(
                lease.normalized_target_path or lease.target_path, normalized_target_path
            ):
                msg = (
                    f"PathIntent conflict: target '{target_path}' overlaps with active lease "
                    f"on '{lease.target_path}' held by '{lease.owner_id}'."
                )
                logger.warning(msg)
                return None, lease.owner_id, msg

        # Acquire lease
        expires_at = now + timedelta(seconds=ttl_seconds)
        lease_domain = domain.PathLease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id=owner_id,
            target_path=target_path,
            normalized_target_path=normalized_target_path,
            is_directory=is_directory,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
            heartbeat_at=now,
            attempt_number=attempt_number,
            worktree_path=worktree_path,
            fencing_token=fencing_token or str(uuid4()),
        )
        orm_obj = PathLeaseORM.from_domain(lease_domain)
        self.session.add(orm_obj)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            msg = f"PathIntent conflict: exact target '{target_path}' was acquired concurrently."
            logger.warning(msg)
            return None, None, msg
        return orm_obj.to_domain(), None, f"Lease acquired for '{target_path}'."

    async def release_lease(
        self,
        lease_id: int,
        reason: LeaseReleaseReason,
        *,
        owner_id: str | None = None,
        fencing_token: str | None = None,
    ) -> domain.PathLease | None:
        """Release a specific path lease."""
        stmt = select(PathLeaseORM).where(PathLeaseORM.id == lease_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            return None
        if owner_id is not None and orm_obj.owner_id != owner_id:
            return None
        if fencing_token is not None and orm_obj.fencing_token != fencing_token:
            return None

        orm_obj.release_reason = reason.value
        orm_obj.active_conflict_key = None
        await self.session.flush()
        return orm_obj.to_domain()

    async def renew_lease(
        self,
        lease_id: int,
        *,
        owner_id: str,
        fencing_token: str,
        ttl_seconds: int | None = None,
    ) -> domain.PathLease | None:
        """Renew an active lease only when the owner still holds the fencing token."""
        now = datetime.now(UTC)
        stmt = select(PathLeaseORM).where(
            PathLeaseORM.id == lease_id,
            PathLeaseORM.owner_id == owner_id,
            PathLeaseORM.fencing_token == fencing_token,
            PathLeaseORM.release_reason.is_(None),
            PathLeaseORM.expires_at > now,
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            return None
        effective_ttl = ttl_seconds if ttl_seconds is not None else orm_obj.ttl_seconds
        orm_obj.ttl_seconds = effective_ttl
        orm_obj.expires_at = now + timedelta(seconds=effective_ttl)
        orm_obj.heartbeat_at = now
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
            lease.active_conflict_key = None
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
