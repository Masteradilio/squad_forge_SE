from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import (
    AutonomyEvaluateRequest,
    VerificationCreateRequest,
    VerificationSubmitRequest,
)
from localforge.models import domain
from localforge.models.enums import AutonomyLevel
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["autonomy"])


@router.post("/autonomy/evaluate")
async def evaluate_autonomy(req: AutonomyEvaluateRequest) -> dict[str, str | bool]:
    """Evaluate whether an action is permitted under the specified AutonomyLevel."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.autonomy is not None
        try:
            level_enum = AutonomyLevel(req.autonomy_level.upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid AutonomyLevel: {req.autonomy_level}"
            ) from exc

        allowed, result_code, reason = uow.autonomy.evaluate_action(
            level=level_enum,
            action_kind=req.action_kind,
            target=req.target,
        )
        return {
            "allowed": allowed,
            "result_code": result_code.value,
            "reason": reason,
        }


@router.post("/verifications", status_code=status.HTTP_201_CREATED)
async def create_verification(req: VerificationCreateRequest) -> domain.MakerCheckerVerification:
    """Initialize a new Maker/Checker verification assignment."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.maker_checker is not None
        try:
            return await uow.maker_checker.create_verification(
                project_id=req.project_id,
                task_run_id=req.task_run_id,
                maker_agent_id=req.maker_agent_id,
                checker_agent_id=req.checker_agent_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/verifications/{verification_id}/submit")
async def submit_verification(
    verification_id: int, req: VerificationSubmitRequest
) -> dict[str, str | bool]:
    """Submit the verification decision from the independent Checker."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.maker_checker is not None
        try:
            ver, result_code, reason = await uow.maker_checker.submit_verification_result(
                verification_id=verification_id,
                checker_agent_id=req.checker_agent_id,
                approved=req.approved,
                deterministic_passed=req.deterministic_passed,
                tests_executed=req.tests_executed,
                not_checked=req.not_checked,
                feedback=req.feedback,
            )
            return {
                "verification_id": ver.id,  # type: ignore[dict-item]
                "status": ver.status.value,
                "result_code": result_code.value,
                "reason": reason,
            }
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/task-runs/{task_run_id}/pr-ready-check")
async def check_pr_ready_eligibility(task_run_id: int) -> dict[str, str | bool]:
    """Check if a task run has a valid, approved Maker/Checker verification required for PR_READY."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.maker_checker is not None
        eligible, reason = await uow.maker_checker.verify_pr_ready_eligibility(task_run_id)
        return {
            "eligible": eligible,
            "reason": reason,
        }


@router.post("/projects/{project_id}/task-runs/{task_run_id}/pre-pr-gate")
async def evaluate_pre_pr_gate(
    project_id: int,
    task_run_id: int,
    diff_text: str = "",
    modified_files: list[str] | None = None,
) -> dict[str, Any]:
    """Run mechanical pre-PR gate checks including secret scanning, file count, and verifier evidence."""
    from localforge.safety.pre_pr_gate import MechanicalPrePRGate

    gate = MechanicalPrePRGate()
    async with UnitOfWork(db_manager) as uow:
        res = await gate.evaluate_gate(
            project_id=project_id,
            task_run_id=task_run_id,
            uow=uow,
            diff_text=diff_text,
            modified_files=modified_files or [],
        )
        return res.to_dict()
