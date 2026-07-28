"""Memory relationships and cycle detection for partial-order relation semantics (V6-1001)."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import MemoryRelationType, MemoryValidityStatus
from localforge.storage.orm import MemoryFactORM, MemoryRelationORM

logger = logging.getLogger(__name__)

PARTIAL_ORDER_RELATIONS = {MemoryRelationType.SUPERSEDES, MemoryRelationType.DERIVED_FROM}


class MemoryRelationService:
    """Manages relationships between memory facts and enforces acyclicity on partial order relations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_relation(
        self,
        source_fact_id: int,
        target_fact_id: int,
        relation_type: MemoryRelationType,
        provenance: dict[str, Any] | None = None,
    ) -> domain.MemoryRelation:
        """Create a relationship between two facts with cycle detection for partial-order relations."""
        if source_fact_id == target_fact_id:
            raise ValueError("Self-referential memory relations are prohibited.")

        # Verify existence of source and target
        source_orm = await self.session.get(MemoryFactORM, source_fact_id)
        target_orm = await self.session.get(MemoryFactORM, target_fact_id)
        if not source_orm or not target_orm:
            raise ValueError("Both source_fact_id and target_fact_id must exist.")

        # If relation is partial-order (SUPERSEDES, DERIVED_FROM), check for cycles
        if relation_type in PARTIAL_ORDER_RELATIONS:
            if await self._would_create_cycle(source_fact_id, target_fact_id, relation_type):
                raise ValueError(
                    f"Relation {relation_type.value} from {source_fact_id} to {target_fact_id} "
                    f"would create a cycle in partial-order relationship semantics."
                )

        # If relation_type is SUPERSEDES, mark target fact as SUPERSEDED (V6-1001)
        if relation_type == MemoryRelationType.SUPERSEDES:
            target_orm.validity = MemoryValidityStatus.SUPERSEDED.value

        # If relation_type is CONTRADICTS, mark target or source as CONTRADICTED
        if relation_type == MemoryRelationType.CONTRADICTS:
            if target_orm.validity == MemoryValidityStatus.AUTHORITATIVE.value:
                target_orm.validity = MemoryValidityStatus.CONTRADICTED.value

        relation = domain.MemoryRelation(
            source_fact_id=source_fact_id,
            target_fact_id=target_fact_id,
            relation_type=relation_type,
            provenance=provenance or {},
        )
        orm_obj = MemoryRelationORM.from_domain(relation)
        self.session.add(orm_obj)
        await self.session.flush()
        relation.id = orm_obj.id
        return relation

    async def list_relations(self, fact_id: int) -> list[domain.MemoryRelation]:
        """List all relations where fact_id is source or target."""
        stmt = select(MemoryRelationORM).where(
            (MemoryRelationORM.source_fact_id == fact_id) | (MemoryRelationORM.target_fact_id == fact_id)
        )
        result = await self.session.execute(stmt)
        return [row.to_domain() for row in result.scalars().all()]

    async def _would_create_cycle(self, source_id: int, target_id: int, relation_type: MemoryRelationType) -> bool:
        """DFS check if adding an edge target_id -> source_id creates a cycle."""
        # Query all existing relations of the same partial-order type
        stmt = select(MemoryRelationORM).where(MemoryRelationORM.relation_type == relation_type.value)
        result = await self.session.execute(stmt)
        all_relations = result.scalars().all()

        adj: dict[int, list[int]] = {}
        for r in all_relations:
            adj.setdefault(r.source_fact_id, []).append(r.target_fact_id)

        # Proposed edge: source_id -> target_id. Check if target_id can already reach source_id.
        visited: set[int] = set()
        queue = [target_id]
        while queue:
            curr = queue.pop(0)
            if curr == source_id:
                return True
            visited.add(curr)
            for nxt in adj.get(curr, []):
                if nxt not in visited:
                    queue.append(nxt)
        return False
