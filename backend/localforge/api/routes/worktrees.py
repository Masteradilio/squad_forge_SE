from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import PathLeaseAcquireRequest, WorktreeManifestCreateRequest
from localforge.models import domain
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["worktrees"])


@router.post("/path-leases/acquire")
async def acquire_path_lease(req: PathLeaseAcquireRequest) -> dict[str, Any]:
    """Attempt to acquire a PathIntent write lease."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        lease, conflict_owner, msg = await uow.path_leases.acquire_lease(
            project_id=req.project_id,
            task_run_id=req.task_run_id,
            owner_id=req.owner_id,
            target_path=req.target_path,
            is_directory=req.is_directory,
            ttl_seconds=req.ttl_seconds,
        )
        if not lease:
            raise HTTPException(status_code=409, detail=msg)
        return {
            "acquired": True,
            "lease_id": lease.id,
            "target_path": lease.target_path,
            "expires_at": lease.expires_at.isoformat(),
        }


@router.get("/projects/{project_id}/path-leases")
async def list_active_path_leases(project_id: int) -> list[domain.PathLease]:
    """List all active unexpired leases for a project."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.path_leases is not None
        return await uow.path_leases.list_active_leases(project_id)


@router.post("/worktree-attempts", status_code=status.HTTP_201_CREATED)
async def create_worktree_manifest(req: WorktreeManifestCreateRequest) -> domain.WorktreeAttemptManifest:
    """Create a new worktree attempt manifest."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.worktrees is not None
        return await uow.worktrees.create_attempt_manifest(
            project_id=req.project_id,
            task_id=req.task_id,
            task_run_id=req.task_run_id,
            worktree_path=req.worktree_path,
            branch_name=req.branch_name,
            source_commit=req.source_commit,
            owner_agent_id=req.owner_agent_id,
            expected_paths=req.expected_paths,
        )


@router.post("/projects/{project_id}/reconciliation/report")
async def reconcile_worktrees(project_id: int) -> dict[str, Any]:
    """Generate a report-only reconciliation of worktree manifests against physical filesystems."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.worktrees is not None
        return await uow.worktrees.reconcile_worktree_manifests(project_id)
