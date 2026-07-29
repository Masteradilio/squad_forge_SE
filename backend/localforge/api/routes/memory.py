from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import (
    MemoryConsolidateRequest,
    MemoryFactCreateRequest,
    MemoryRelationCreateRequest,
    MemoryRetrieveRequest,
)
from localforge.models import domain
from localforge.models.enums import (
    MemoryFactCategory,
    MemoryRecordKind,
    MemoryRelationType,
    MemoryValidityStatus,
)
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["memory"])


@router.post("/memory/facts", status_code=status.HTTP_201_CREATED)
async def create_memory_fact(req: MemoryFactCreateRequest) -> domain.MemoryFact:
    """Create a new memory fact with provenance tracking (V6-1000)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        fact = domain.MemoryFact(
            project_id=req.project_id,
            fact=req.fact,
            kind=MemoryRecordKind(req.kind),
            source=req.source,
            category=MemoryFactCategory(req.category),
            validity=MemoryValidityStatus(req.validity),
            confidence=req.confidence,
            pinned=req.pinned,
            repository=req.repository,
            run_id=req.run_id,
            task_key=req.task_key,
            attempt_number=req.attempt_number,
            artifact_id=req.artifact_id,
            verifier=req.verifier,
            policy_scope=req.policy_scope,
            tags=req.tags,
        )
        return await uow.memory.create_fact(fact)


@router.get("/memory/facts")
async def list_memory_facts(
    project_id: int,
    category: str | None = None,
    validity: str | None = None,
) -> list[domain.MemoryFact]:
    """List memory facts filtered by category or validity."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        cat_enum = MemoryFactCategory(category) if category else None
        val_enum = MemoryValidityStatus(validity) if validity else None
        return await uow.memory.list_facts(project_id, category=cat_enum, validity=val_enum)


@router.patch("/memory/facts/{fact_id}")
async def update_memory_fact(
    fact_id: int,
    fact: str | None = None,
    pinned: bool | None = None,
    status_str: str | None = None,
    validity: str | None = None,
) -> domain.MemoryFact:
    """Human override operation: update, pin, invalidate or supersede a memory fact (V6-1004)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        val_enum = MemoryValidityStatus(validity) if validity else None
        try:
            return await uow.memory.update_fact(
                fact_id,
                fact=fact,
                pinned=pinned,
                status=status_str,
                validity=val_enum,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/memory/relations", status_code=status.HTTP_201_CREATED)
async def create_memory_relation(req: MemoryRelationCreateRequest) -> domain.MemoryRelation:
    """Create a relationship between memory facts with cycle detection (V6-1001)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        try:
            rel_type = MemoryRelationType(req.relation_type)
            return await uow.memory.add_relation(
                source_fact_id=req.source_fact_id,
                target_fact_id=req.target_fact_id,
                relation_type=rel_type,
                provenance=req.provenance,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/memory/consolidate")
async def consolidate_memory(req: MemoryConsolidateRequest) -> dict[str, Any]:
    """Run background memory consolidation job (V6-1002)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        policy = domain.MemoryRetentionPolicy(
            max_fact_age_days=req.max_fact_age_days,
            deduplication_threshold=req.deduplication_threshold,
        )
        return await uow.memory.consolidate_memory(req.project_id, policy)


@router.post("/memory/retrieve")
async def retrieve_memory(req: MemoryRetrieveRequest) -> list[domain.MemoryFact]:
    """Structured and lexical memory retrieval (V6-1003)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        cat_enum = MemoryFactCategory(req.category) if req.category else None
        val_enum = MemoryValidityStatus(req.validity) if req.validity else None
        filters = domain.MemoryRetrievalFilter(
            task_key=req.task_key,
            category=cat_enum,
            validity=val_enum,
        )
        return await uow.memory.retrieve_advanced(
            req.project_id,
            query=req.query,
            filters=filters,
            limit=req.limit,
        )


@router.get("/memory/inject")
async def inject_memory_context(project_id: int, task_key: str, query: str = "") -> dict[str, str]:
    """Get safe read-only memory context for prompt injection (V6-1004)."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.memory is not None
        prompt_text = await uow.memory.inject_scoped_memory(project_id, task_key, query=query)
        return {"task_key": task_key, "prompt_context": prompt_text}
