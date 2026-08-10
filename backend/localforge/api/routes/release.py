"""API surface for durable release promotion approvals."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from localforge.api.schemas import ReleaseApprovalRequest
from localforge.control_plane import (
    ControlPlaneKernel,
    ControlPlaneStore,
    goal_id_for_project,
    state_path_for_goal,
)
from localforge.models.enums import ActionApprovalStatus, RunStatus
from localforge.services.release_promotion import (
    ReleasePromotionResult,
    ReleasePromotionService,
    ReleasePromotionState,
)
from localforge.storage import DatabaseManager, UnitOfWork


def _mark_control_plane_release_completed(
    manager: DatabaseManager,
    project: Any,
    run: Any,
    result: ReleasePromotionResult,
) -> None:
    if result.state != ReleasePromotionState.COMPLETED or project.id is None or run.id is None:
        return
    database_identity = getattr(manager, "db_url", "default")
    if ":memory:" in str(database_identity):
        database_identity = f"{database_identity}:instance:{id(manager)}"
    goal_id = goal_id_for_project(project.id, run.resource_limits)
    state_path = state_path_for_goal(project.root_path, goal_id, database_identity)
    kernel = ControlPlaneKernel(ControlPlaneStore(state_path))
    if kernel.status() is None:
        return
    kernel.mark_release_completed(
        summary=result.reason,
        evidence={
            "run_id": run.id,
            "release_state": result.state.value,
            "merge_commit": result.merge_commit,
            "post_merge_results": result.post_merge_results,
        },
    )


def create_release_router(manager: DatabaseManager) -> APIRouter:
    router = APIRouter(tags=["release"])

    @router.get("/projects/{project_id}/runs/{run_id}/release")
    async def release_status(project_id: int, run_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None and uow.executions is not None and uow.safety is not None
            project = await uow.projects.get_project(project_id)
            run = await uow.executions.get_run(run_id)
            if project is None or run is None or run.project_id != project_id:
                raise HTTPException(status_code=404, detail="Run not found")
            approvals = await uow.safety.list_approvals_for_run(run_id)
            return {
                "run_id": run_id,
                "run_status": run.status.value,
                "release": (run.resource_limits or {}).get("release_promotion", {}),
                "pending_approvals": [
                    item.model_dump(mode="json")
                    for item in approvals
                    if item.status == ActionApprovalStatus.PENDING
                ],
            }

    @router.post("/projects/{project_id}/runs/{run_id}/release/approve")
    async def approve_release(
        project_id: int,
        run_id: int,
        request: ReleaseApprovalRequest,
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None and uow.executions is not None and uow.safety is not None
            project = await uow.projects.get_project(project_id)
            run = await uow.executions.get_run(run_id)
            if project is None or run is None or run.project_id != project_id:
                raise HTTPException(status_code=404, detail="Run not found")
            release = dict((run.resource_limits or {}).get("release_promotion") or {})
            approvals = await uow.safety.list_approvals_for_run(run_id)
            approval_id = release.get("approval_id")
            approval = next(
                (item for item in approvals if item.id == approval_id),
                next((item for item in approvals if item.status == ActionApprovalStatus.PENDING), None),
            )
            if approval is None:
                if release.get("state") == "COMPLETED":
                    return {"run_id": run_id, "release_state": "COMPLETED", "release": release}
                raise HTTPException(status_code=409, detail="No pending release approval found")
            if approval.status == ActionApprovalStatus.PENDING:
                approval.status = ActionApprovalStatus.APPROVED
                approval.decided_at = datetime.now(UTC)
                approval.decided_by = request.approver_id
                approval.decision_nonce = secrets.token_hex(16)
                approval.decision_reason = request.reason
                approval.idempotency_key = approval.idempotency_key or request.idempotency_key
                await uow.safety.update_approval(approval)
            release.update({"approval_id": approval.id, "approval_granted": True})
            run.resource_limits = dict(run.resource_limits or {})
            run.resource_limits["release_promotion"] = release
            run.status = RunStatus.RUNNING
            await uow.executions.update_run(run)
            assert uow.session is not None
            await uow.session.commit()

            result = await ReleasePromotionService(
                uow,
                project_id=project_id,
                run_id=run_id,
            ).promote(approval_granted=True)
            _mark_control_plane_release_completed(manager, project, run, result)
            refreshed = await uow.executions.get_run(run_id)
            if refreshed is not None and result.state.value == "COMPLETED":
                refreshed.status = RunStatus.COMPLETED
                refreshed.ended_at = datetime.now(UTC)
                await uow.executions.update_run(refreshed)
                await uow.session.commit()
            return {
                "run_id": run_id,
                "approval_id": approval.id,
                "release_state": result.state.value,
                "reason": result.reason,
                "merge_commit": result.merge_commit,
                "post_merge_results": result.post_merge_results,
            }

    return router
