import logging
import posixpath
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import LeaseReleaseReason, PathLeaseWaitStatus
from localforge.storage.orm import PathLeaseORM, PathLeaseWaitORM

logger = logging.getLogger(__name__)


def normalize_lease_path(path: str) -> str:
    """Normalize a lease path into a comparable repository-relative form."""
    normalized = posixpath.normpath(path.replace("\\", "/")).strip("/")
    normalized = str(PurePosixPath(normalized))
    return normalized.lower()


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


def canonicalize_repository_relative_path(target_path: str, repository_root: str) -> str:
    """Resolve a target path through the repository root and reject boundary escape."""
    root = Path(repository_root).resolve(strict=False)
    target = Path(target_path)
    if not target.is_absolute():
        target = root / target
    resolved_target = target.resolve(strict=False)
    try:
        relative = resolved_target.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"PathIntent boundary violation: target '{target_path}' resolves outside repository root."
        ) from exc
    return normalize_lease_path(relative.as_posix())


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
        repository_root: str | None = None,
    ) -> tuple[domain.PathLease | None, str | None, str]:
        """Attempt to acquire an exclusive write lease for a target path.

        Returns:
            (lease: PathLease | None, conflict_owner_id: str | None, message: str)
        """
        now = datetime.now(UTC)
        try:
            normalized_target_path = (
                canonicalize_repository_relative_path(target_path, repository_root)
                if repository_root is not None
                else normalize_lease_path(target_path)
            )
        except ValueError as exc:
            msg = str(exc)
            logger.warning(msg)
            return None, None, msg
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

    async def acquire_or_wait(
        self,
        project_id: int,
        task_run_id: int,
        owner_id: str,
        target_path: str,
        is_directory: bool = False,
        ttl_seconds: int = 3600,
        wait_timeout_seconds: int = 300,
        attempt_number: int = 1,
        worktree_path: str | None = None,
        fencing_token: str | None = None,
        repository_root: str | None = None,
    ) -> tuple[domain.PathLease | None, domain.PathLeaseWait | None, str]:
        """Acquire a path lease or persist a bounded wait-for edge when it is blocked."""
        lease, conflict_owner, message = await self.acquire_lease(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id=owner_id,
            target_path=target_path,
            is_directory=is_directory,
            ttl_seconds=ttl_seconds,
            attempt_number=attempt_number,
            worktree_path=worktree_path,
            fencing_token=fencing_token,
            repository_root=repository_root,
        )
        if lease is not None or conflict_owner is None:
            return lease, None, message

        wait = await self.enqueue_wait(
            project_id=project_id,
            task_run_id=task_run_id,
            owner_id=owner_id,
            target_path=target_path,
            blocking_owner_id=conflict_owner,
            timeout_seconds=wait_timeout_seconds,
            repository_root=repository_root,
        )
        return None, wait, message

    async def enqueue_wait(
        self,
        project_id: int,
        task_run_id: int,
        owner_id: str,
        target_path: str,
        blocking_owner_id: str,
        *,
        blocking_lease_id: int | None = None,
        timeout_seconds: int = 300,
        repository_root: str | None = None,
    ) -> domain.PathLeaseWait:
        """Persist a FIFO wait edge and mark a deterministic deadlock victim for 2-cycles."""
        now = datetime.now(UTC)
        normalized_target_path = (
            canonicalize_repository_relative_path(target_path, repository_root)
            if repository_root is not None
            else normalize_lease_path(target_path)
        )
        await self.expire_waits(now=now)

        existing_stmt = select(PathLeaseWaitORM).where(
            PathLeaseWaitORM.project_id == project_id,
            PathLeaseWaitORM.owner_id == owner_id,
            PathLeaseWaitORM.normalized_target_path == normalized_target_path,
            PathLeaseWaitORM.status == PathLeaseWaitStatus.WAITING.value,
        )
        existing_result = await self.session.execute(existing_stmt)
        existing_wait = existing_result.scalar_one_or_none()
        if existing_wait is not None:
            return existing_wait.to_domain()

        queue_stmt = select(PathLeaseWaitORM).where(
            PathLeaseWaitORM.project_id == project_id,
            PathLeaseWaitORM.normalized_target_path == normalized_target_path,
            PathLeaseWaitORM.status == PathLeaseWaitStatus.WAITING.value,
        )
        queue_result = await self.session.execute(queue_stmt)
        queue_position = len(queue_result.scalars().all()) + 1

        wait = PathLeaseWaitORM.from_domain(
            domain.PathLeaseWait(
                project_id=project_id,
                task_run_id=task_run_id,
                owner_id=owner_id,
                target_path=target_path,
                normalized_target_path=normalized_target_path,
                blocking_owner_id=blocking_owner_id,
                blocking_lease_id=blocking_lease_id,
                queue_position=queue_position,
                requested_at=now,
                expires_at=now + timedelta(seconds=timeout_seconds),
                reason=f"Waiting for path lease held by '{blocking_owner_id}'.",
            )
        )
        self.session.add(wait)
        await self.session.flush()

        cycle_stmt = select(PathLeaseWaitORM).where(
            PathLeaseWaitORM.project_id == project_id,
            PathLeaseWaitORM.owner_id == blocking_owner_id,
            PathLeaseWaitORM.blocking_owner_id == owner_id,
            PathLeaseWaitORM.status == PathLeaseWaitStatus.WAITING.value,
        )
        cycle_result = await self.session.execute(cycle_stmt)
        peer_wait = cycle_result.scalar_one_or_none()
        if peer_wait is not None:
            victim = max(owner_id, blocking_owner_id)
            victim_wait = wait if wait.owner_id == victim else peer_wait
            victim_wait.status = PathLeaseWaitStatus.DEADLOCK_VICTIM.value
            victim_wait.resolved_at = now
            victim_wait.reason = (
                "Deadlock detected in path lease wait-for graph; "
                f"'{victim}' selected as deterministic victim."
            )
            await self.session.flush()

        return wait.to_domain()

    async def cancel_wait(
        self,
        wait_id: int,
        *,
        owner_id: str | None = None,
        reason: str = "Wait cancelled.",
    ) -> domain.PathLeaseWait | None:
        """Cancel a pending path lease wait edge."""
        stmt = select(PathLeaseWaitORM).where(
            PathLeaseWaitORM.id == wait_id,
            PathLeaseWaitORM.status == PathLeaseWaitStatus.WAITING.value,
        )
        if owner_id is not None:
            stmt = stmt.where(PathLeaseWaitORM.owner_id == owner_id)
        result = await self.session.execute(stmt)
        wait = result.scalar_one_or_none()
        if wait is None:
            return None
        wait.status = PathLeaseWaitStatus.CANCELLED.value
        wait.resolved_at = datetime.now(UTC)
        wait.reason = reason
        await self.session.flush()
        return wait.to_domain()

    async def expire_waits(self, *, now: datetime | None = None) -> int:
        """Mark overdue wait edges as timed out."""
        effective_now = now or datetime.now(UTC)
        stmt = select(PathLeaseWaitORM).where(
            PathLeaseWaitORM.status == PathLeaseWaitStatus.WAITING.value,
            PathLeaseWaitORM.expires_at <= effective_now,
        )
        result = await self.session.execute(stmt)
        waits = result.scalars().all()
        for wait in waits:
            wait.status = PathLeaseWaitStatus.TIMED_OUT.value
            wait.resolved_at = effective_now
            wait.reason = "Path lease wait timed out."
        await self.session.flush()
        return len(waits)

    async def list_waits_for_project(
        self,
        project_id: int,
        *,
        status: PathLeaseWaitStatus | None = None,
    ) -> list[domain.PathLeaseWait]:
        """List persisted path lease wait edges for a project."""
        stmt = select(PathLeaseWaitORM).where(PathLeaseWaitORM.project_id == project_id)
        if status is not None:
            stmt = stmt.where(PathLeaseWaitORM.status == status.value)
        stmt = stmt.order_by(PathLeaseWaitORM.requested_at, PathLeaseWaitORM.id)
        result = await self.session.execute(stmt)
        return [wait.to_domain() for wait in result.scalars().all()]

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
