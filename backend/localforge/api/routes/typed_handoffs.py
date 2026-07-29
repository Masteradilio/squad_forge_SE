from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import TypedHandoffCreateRequest
from localforge.models import domain
from localforge.models.enums import TypedArtifactType
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["typed-handoffs"])


@router.post("/handoff-artifacts", status_code=status.HTTP_201_CREATED)
async def create_typed_handoff_artifact(
    req: TypedHandoffCreateRequest,
) -> domain.TypedHandoffArtifact:
    """Create a new validated TypedHandoffArtifact with SHA-256 content_hash."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.typed_handoffs is not None
        return await uow.typed_handoffs.create_artifact(
            project_id=req.project_id,
            task_run_id=req.task_run_id,
            producer_agent_id=req.producer_agent_id,
            consumer_agent_id=req.consumer_agent_id,
            summary=req.summary,
            artifact_type=TypedArtifactType(req.artifact_type),
            schema_version=req.schema_version,
            evidence_json=req.evidence_json,
            changed_files=req.changed_files,
            tests_executed=req.tests_executed,
            validation_results_json=req.validation_results_json,
            open_questions=req.open_questions,
            risks=req.risks,
            not_checked=req.not_checked,
        )


@router.get("/handoff-artifacts/{artifact_id}/validate")
async def validate_artifact_integrity(artifact_id: int) -> dict[str, Any]:
    """Validate content_hash integrity of a stored handoff artifact."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.typed_handoffs is not None
        valid, msg = await uow.typed_handoffs.validate_artifact_integrity(artifact_id)
        if not valid:
            raise HTTPException(status_code=422, detail=msg)
        return {"valid": True, "artifact_id": artifact_id}


@router.post("/handoff-artifacts/{artifact_id}/consume")
async def consume_artifact(artifact_id: int) -> domain.TypedHandoffArtifact:
    """Enforce consume-once semantics for specified handoff artifact."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.typed_handoffs is not None
        try:
            return await uow.typed_handoffs.consume_artifact(artifact_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/task-runs/{task_run_id}/handoff-artifacts")
async def list_artifacts_for_run(task_run_id: int) -> list[domain.TypedHandoffArtifact]:
    """List all typed handoff artifacts produced during a task run."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.typed_handoffs is not None
        return await uow.typed_handoffs.list_artifacts_for_run(task_run_id)
