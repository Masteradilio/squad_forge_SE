"""Release promotion controls for human-gated and full-access runs."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime
from typing import Any

import typer
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
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console

console = Console()
release_app = typer.Typer(help="Promote PR_READY branches and inspect release gates.")


def _mark_control_plane_release_completed(
    project: Any,
    run: Any,
    result: ReleasePromotionResult,
) -> None:
    if result.state != ReleasePromotionState.COMPLETED or project.id is None or run.id is None:
        return
    database_identity = getattr(db_manager, "db_url", "default")
    if ":memory:" in str(database_identity):
        database_identity = f"{database_identity}:instance:{id(db_manager)}"
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


async def _current_project(uow: UnitOfWork):
    assert uow.projects is not None
    project = await uow.projects.get_project_by_path(os.getcwd())
    if not project:
        raise typer.BadParameter("workspace is not initialized")
    return project


async def _select_run(uow: UnitOfWork, project_id: int, run_id: int | None):
    assert uow.executions is not None
    if run_id is not None:
        run = await uow.executions.get_run(run_id)
        if run is None or run.project_id != project_id:
            raise typer.BadParameter(f"run {run_id} not found in the current project")
        return run
    runs = await uow.executions.list_runs_for_project(project_id)
    if not runs:
        raise typer.BadParameter("no runs recorded for the current project")
    return runs[0]


@release_app.command("status")
def release_status_cmd(
    run_id: int | None = typer.Option(None, "--run-id"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show the persisted release promotion state and pending approval."""

    async def execute() -> None:
        async with UnitOfWork(db_manager) as uow:
            project = await _current_project(uow)
            assert project.id is not None and uow.safety is not None
            run = await _select_run(uow, project.id, run_id)
            approvals = await uow.safety.list_approvals_for_run(run.id or -1)
            payload: dict[str, Any] = {
                "run_id": run.id,
                "run_status": run.status.value,
                "release": (run.resource_limits or {}).get("release_promotion", {}),
                "pending_approvals": [
                    item.model_dump(mode="json")
                    for item in approvals
                    if item.status == ActionApprovalStatus.PENDING
                ],
            }
            if json_output:
                console.print_json(json.dumps(payload))
            else:
                console.print_json(json.dumps(payload))

    asyncio.run(execute())


@release_app.command("approve")
def release_approve_cmd(
    run_id: int | None = typer.Option(None, "--run-id"),
    approver_id: str = typer.Option("local-human", "--approver-id"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    reason: str = typer.Option("Approved release promotion after PR_READY review.", "--reason"),
) -> None:
    """Approve and execute one waiting release promotion exactly once."""

    async def execute() -> None:
        async with UnitOfWork(db_manager) as uow:
            project = await _current_project(uow)
            assert project.id is not None
            assert uow.safety is not None and uow.executions is not None
            run = await _select_run(uow, project.id, run_id)
            release = dict((run.resource_limits or {}).get("release_promotion") or {})
            approval_id = release.get("approval_id")
            approvals = await uow.safety.list_approvals_for_run(run.id or -1)
            approval = next(
                (item for item in approvals if item.id == approval_id),
                next((item for item in approvals if item.status == ActionApprovalStatus.PENDING), None),
            )
            if approval is None:
                raise typer.BadParameter("no pending release approval found for this run")
            key = idempotency_key or f"release-approve:{run.id}"
            if approval.status == ActionApprovalStatus.PENDING:
                approval.status = ActionApprovalStatus.APPROVED
                approval.decided_at = datetime.now(UTC)
                approval.decided_by = approver_id
                approval.decision_nonce = secrets.token_hex(16)
                approval.decision_reason = reason
                approval.idempotency_key = approval.idempotency_key or key
                await uow.safety.update_approval(approval)
            release["approval_granted"] = True
            release["approval_id"] = approval.id
            run.resource_limits = dict(run.resource_limits or {})
            run.resource_limits["release_promotion"] = release
            run.status = RunStatus.RUNNING
            await uow.executions.update_run(run)
            assert uow.session is not None
            await uow.session.commit()

            result = await ReleasePromotionService(
                uow,
                project_id=project.id,
                run_id=run.id or -1,
            ).promote(approval_granted=True)
            _mark_control_plane_release_completed(project, run, result)
            refreshed = await uow.executions.get_run(run.id or -1)
            if refreshed is not None and result.state.value == "COMPLETED":
                refreshed.status = RunStatus.COMPLETED
                refreshed.ended_at = datetime.now(UTC)
                await uow.executions.update_run(refreshed)
                await uow.session.commit()
            console.print_json(
                json.dumps(
                    {
                        "run_id": run.id,
                        "approval_id": approval.id,
                        "approver_id": approver_id,
                        "release_state": result.state.value,
                        "reason": result.reason,
                        "merge_commit": result.merge_commit,
                    }
                )
            )

    asyncio.run(execute())
