"""Reference-to-product continuity API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import BlueprintRequest, ReferenceDecisionRequest, ReferenceIngestRequest, ReferenceSearchRequest
from localforge.services.reference_continuity import ReferenceContinuityError
from localforge.storage import DatabaseManager, UnitOfWork


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def create_references_router(manager: DatabaseManager) -> APIRouter:
    router = APIRouter(tags=["references"])

    async def fail(exc: Exception) -> None:
        if isinstance(exc, ReferenceContinuityError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise exc

    @router.post("/projects/{project_id}/references", status_code=status.HTTP_201_CREATED)
    async def ingest(project_id: int, req: ReferenceIngestRequest) -> dict[str, Any]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.references is not None
                return _dump(
                    await uow.references.ingest_text(
                        project_id=project_id, name=req.name, content=req.content, source_type=req.source_type, path=req.path, metadata=req.metadata
                    )
                )
        except Exception as exc:
            await fail(exc)
            raise AssertionError("unreachable") from exc

    @router.get("/projects/{project_id}/references")
    async def sources(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.references is not None
            return [_dump(item) for item in await uow.references.list_sources(project_id)]

    @router.post("/projects/{project_id}/references/search")
    async def search(project_id: int, req: ReferenceSearchRequest) -> list[dict[str, Any]]:
        async with UnitOfWork(manager, read_only=True) as uow:
            assert uow.references is not None
            return await uow.references.search(project_id=project_id, query=req.query, limit=req.limit)

    @router.post("/projects/{project_id}/reference-decisions", status_code=status.HTTP_201_CREATED)
    async def decide(project_id: int, req: ReferenceDecisionRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.references is not None
            return _dump(
                await uow.references.decide(
                    project_id=project_id,
                    query=req.query,
                    summary=req.summary,
                    selected_chunk_ids=req.selected_chunk_ids,
                    turn_id=req.turn_id,
                    decision=req.decision,
                )
            )

    @router.post("/projects/{project_id}/product-blueprints", status_code=status.HTTP_201_CREATED)
    async def blueprint(project_id: int, req: BlueprintRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.references is not None
            return _dump(await uow.references.build_blueprint(project_id=project_id, name=req.name, decision_id=req.decision_id, freeze=req.freeze))

    @router.get("/projects/{project_id}/product-blueprints/{blueprint_id}")
    async def get_blueprint(project_id: int, blueprint_id: str) -> dict[str, Any]:
        async with UnitOfWork(manager, read_only=True) as uow:
            assert uow.references is not None
            return _dump(await uow.references.get_blueprint(project_id, blueprint_id))

    return router
