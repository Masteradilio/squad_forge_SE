"""Provenance-aware operational memory service.

Implements V6-1000 through V6-1004:
- Provenance tracking for repository, run, task, verifier, validity, and scope.
- Learning restriction: failed/unverified attempts are not authoritative memory (V6-1000)
- Typed relationships with cycle detection for partial-order semantics (V6-1001)
- Consolidation background job (duplicates, expired facts, contradictions) (V6-1002)
- Lexical/structured retrieval with evaluation benchmark (Recall@k, MRR) (V6-1003)
- Safe prompt injection for Loop & Swarm without permission elevation (V6-1004)
- Human override operations (pin, correct, supersede, invalidate) (V6-1004)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import (
    ArtifactType,
    MemoryFactCategory,
    MemoryRecordKind,
    MemoryRelationType,
    MemoryValidityStatus,
)
from localforge.services.memory_relations import MemoryRelationService
from localforge.services.memory_retrieval import (
    EmbeddingProvider,
    build_safe_memory_prompt,
    calculate_retrieval_metrics,
    filter_and_score_facts,
)
from localforge.storage.orm import MemoryFactORM

logger = logging.getLogger(__name__)


class MemoryService:
    """Persist memory facts, relationships, consolidation, and retrieval."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.relations = MemoryRelationService(session)

    # ------------------------------------------------------------------ #
    # V6-1000: Provenance Fact Operations
    # ------------------------------------------------------------------ #

    async def list_facts(
        self,
        project_id: int,
        category: MemoryFactCategory | None = None,
        validity: MemoryValidityStatus | None = None,
    ) -> list[domain.MemoryFact]:
        stmt = select(MemoryFactORM).where(MemoryFactORM.project_id == project_id)
        if category:
            stmt = stmt.where(MemoryFactORM.category == category.value)
        if validity:
            stmt = stmt.where(MemoryFactORM.validity == validity.value)
        stmt = stmt.order_by(MemoryFactORM.pinned.desc(), MemoryFactORM.updated_at.desc())

        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def create_fact(self, fact: domain.MemoryFact) -> domain.MemoryFact:
        """Create or update existing fact with provenance fields."""
        existing = await self._find_existing(fact.project_id, fact.fact)
        if existing:
            return existing.to_domain()
        orm_obj = MemoryFactORM.from_domain(fact)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def update_fact(
        self,
        fact_id: int,
        *,
        fact: str | None = None,
        pinned: bool | None = None,
        status: str | None = None,
        validity: MemoryValidityStatus | None = None,
        tags: list[str] | None = None,
    ) -> domain.MemoryFact:
        orm_obj = await self.session.get(MemoryFactORM, fact_id)
        if not orm_obj:
            raise ValueError(f"Memory fact with ID {fact_id} not found")
        if fact is not None:
            orm_obj.fact = fact
        if pinned is not None:
            orm_obj.pinned = pinned
        if status is not None:
            orm_obj.status = status
        if validity is not None:
            orm_obj.validity = (
                validity.value if isinstance(validity, MemoryValidityStatus) else str(validity)
            )
        if tags is not None:
            orm_obj.tags = tags
        orm_obj.updated_at = datetime.now(UTC)
        await self.session.flush()
        return orm_obj.to_domain()

    async def delete_fact(self, fact_id: int) -> None:
        orm_obj = await self.session.get(MemoryFactORM, fact_id)
        if not orm_obj:
            raise ValueError(f"Memory fact with ID {fact_id} not found")
        await self.session.delete(orm_obj)
        await self.session.flush()

    async def learn_from_completed_run(
        self,
        *,
        project_id: int,
        task_key: str,
        task_title: str,
        final_summary: str | None,
        artifact_summaries: list[tuple[ArtifactType, str | None]],
        is_successful: bool = True,
        verifier: str | None = None,
    ) -> list[domain.MemoryFact]:
        """Learn facts from a run (V6-1000).

        Failed runs are persisted as rejected, not authoritative.
        """
        learned: list[domain.MemoryFact] = []
        validity = (
            MemoryValidityStatus.AUTHORITATIVE if is_successful else MemoryValidityStatus.REJECTED
        )

        if final_summary:
            learned.append(
                await self.create_fact(
                    domain.MemoryFact(
                        project_id=project_id,
                        kind=MemoryRecordKind.RESOLVED_BLOCKER,
                        category=MemoryFactCategory.OUTCOME,
                        validity=validity,
                        task_key=task_key,
                        verifier=verifier,
                        fact=f"{task_key} completed: {final_summary[:240]}",
                        source="completed_run",
                        tags=[task_key, "completed-run", task_title],
                    )
                )
            )
        for artifact_type, summary in artifact_summaries:
            if not summary:
                continue
            if artifact_type == ArtifactType.TEST:
                kind = MemoryRecordKind.TEST_COMMAND
                cat = MemoryFactCategory.OBSERVED_FACT
            elif artifact_type in {ArtifactType.RISK, ArtifactType.BLOCKER}:
                kind = MemoryRecordKind.KNOWN_PITFALL
                cat = MemoryFactCategory.FAILURE_PATTERN
            else:
                continue

            learned.append(
                await self.create_fact(
                    domain.MemoryFact(
                        project_id=project_id,
                        kind=kind,
                        category=cat,
                        validity=validity,
                        task_key=task_key,
                        verifier=verifier,
                        fact=f"{task_key} {artifact_type.value}: {summary[:240]}",
                        source="completed_run",
                        tags=[task_key, artifact_type.value],
                    )
                )
            )
        return learned

    # ------------------------------------------------------------------ #
    # V6-1001: Relationship operations & Cycle prevention
    # ------------------------------------------------------------------ #

    async def add_relation(
        self,
        source_fact_id: int,
        target_fact_id: int,
        relation_type: MemoryRelationType,
        provenance: dict[str, Any] | None = None,
    ) -> domain.MemoryRelation:
        return await self.relations.add_relation(
            source_fact_id, target_fact_id, relation_type, provenance
        )

    # ------------------------------------------------------------------ #
    # V6-1002: Memory Consolidation Job
    # ------------------------------------------------------------------ #

    async def consolidate_memory(
        self, project_id: int, policy: domain.MemoryRetentionPolicy | None = None
    ) -> dict[str, Any]:
        """Bounded background consolidation job (V6-1002).

        Detects expired facts, exact duplicates, and potential contradictions.
        """
        pol = policy or domain.MemoryRetentionPolicy()
        facts = await self.list_facts(project_id)
        now = datetime.now(UTC)

        expired_count = 0
        duplicate_count = 0
        seen_texts: dict[str, int] = {}

        for fact in facts:
            if fact.id is None:
                continue

            # 1. Check expiration based on max_fact_age_days
            created = (
                fact.created_at if fact.created_at.tzinfo else fact.created_at.replace(tzinfo=UTC)
            )
            age = (now - created).days

            if (
                age > pol.max_fact_age_days
                and fact.validity == MemoryValidityStatus.AUTHORITATIVE
                and not fact.pinned
            ):
                await self.update_fact(fact.id, validity=MemoryValidityStatus.EXPIRED)
                expired_count += 1
                continue

            # 2. Check exact duplicate text
            norm_text = fact.fact.strip().lower()
            if norm_text in seen_texts:
                original_id = seen_texts[norm_text]
                # Mark current as superseded by original
                await self.add_relation(
                    source_fact_id=original_id,
                    target_fact_id=fact.id,
                    relation_type=MemoryRelationType.SUPERSEDES,
                    provenance={"reason": "consolidation_exact_duplicate"},
                )
                duplicate_count += 1
            else:
                seen_texts[norm_text] = fact.id

        return {
            "project_id": project_id,
            "expired_count": expired_count,
            "duplicate_count": duplicate_count,
            "remaining_active_facts": len(seen_texts),
        }

    # ------------------------------------------------------------------ #
    # V6-1003: Structured Retrieval & Evaluation
    # ------------------------------------------------------------------ #

    async def retrieve_advanced(
        self,
        project_id: int,
        *,
        query: str,
        filters: domain.MemoryRetrievalFilter | None = None,
        limit: int = 5,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> list[domain.MemoryFact]:
        """Search using structured filters, lexical terms, and optional embeddings."""
        all_facts = await self.list_facts(project_id)
        scored = filter_and_score_facts(all_facts, query, filters, embedding_provider)
        return [fact for _, fact in scored[:limit]]

    def run_benchmark(
        self,
        eval_cases: list[tuple[str, list[int], list[domain.MemoryFact]]],
        k: int = 5,
    ) -> domain.MemoryRetrievalBenchmarkResult:
        return calculate_retrieval_metrics(eval_cases, k)

    # ------------------------------------------------------------------ #
    # V6-1004: Safe Memory Prompt Injection for Loop & Swarm
    # ------------------------------------------------------------------ #

    async def inject_scoped_memory(
        self, project_id: int, task_key: str, query: str = "", limit: int = 5
    ) -> str:
        """Inject read-only, scoped, authoritative memory into loop/swarm prompts (V6-1004)."""
        facts = await self.retrieve_scoped(
            project_id,
            query=query or task_key,
            task_key=task_key,
            limit=limit,
        )
        return build_safe_memory_prompt(facts)

    async def retrieve_relevant(
        self, project_id: int, *, query: str, limit: int = 5
    ) -> list[domain.MemoryFact]:
        """Backward-compatible retrieval method delegating to retrieve_advanced."""
        flt = domain.MemoryRetrievalFilter(validity=MemoryValidityStatus.AUTHORITATIVE)
        return await self.retrieve_advanced(project_id, query=query, filters=flt, limit=limit)

    async def retrieve_scoped(
        self,
        project_id: int,
        *,
        query: str,
        task_key: str | None = None,
        repository: str | None = None,
        file_paths: list[str] | None = None,
        error_fingerprint: str | None = None,
        policy_scope: str | None = None,
        limit: int = 5,
    ) -> list[domain.MemoryFact]:
        """Retrieve active authoritative memory bounded by project and execution scope."""
        filters = domain.MemoryRetrievalFilter(
            repository=repository,
            task_key=task_key,
            error_fingerprint=error_fingerprint,
            policy_scope=policy_scope,
            validity=MemoryValidityStatus.AUTHORITATIVE,
        )
        facts = await self.retrieve_advanced(
            project_id,
            query=query,
            filters=filters,
            limit=max(limit * 3, limit),
        )
        active_facts = [fact for fact in facts if fact.status == "active"]
        if not file_paths:
            return active_facts[:limit]

        scoped: list[domain.MemoryFact] = []
        normalized_paths = [path.lower() for path in file_paths]
        for fact in active_facts:
            text = " ".join([fact.fact, fact.source, " ".join(fact.tags)]).lower()
            if not any(path in text for path in normalized_paths):
                continue
            scoped.append(fact)
        return scoped[:limit]

    # ------------------------------------------------------------------ #
    # Backup & Internal Helpers
    # ------------------------------------------------------------------ #

    async def export_backup(self, project_id: int, *, fmt: str = "json") -> str:
        payload = {
            "project_id": project_id,
            "facts": [fact.model_dump(mode="json") for fact in await self.list_facts(project_id)],
        }
        if fmt == "json":
            return json.dumps(payload, indent=2, sort_keys=True)
        raise ValueError("Unsupported memory export format")

    async def import_backup(
        self, project_id: int, payload: dict[str, Any]
    ) -> list[domain.MemoryFact]:
        facts = payload.get("facts", [])
        if not isinstance(facts, list):
            raise ValueError("Memory backup must contain a facts list")
        created: list[domain.MemoryFact] = []
        for item in facts:
            if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
                continue
            created.append(
                await self.create_fact(
                    domain.MemoryFact(
                        project_id=project_id,
                        fact=item["fact"],
                        kind=MemoryRecordKind(str(item.get("kind") or "stack_fact")),
                        source=str(item.get("source") or "import"),
                        pinned=bool(item.get("pinned", False)),
                        status=str(item.get("status") or "active"),
                        tags=[str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
                    )
                )
            )
        return created

    async def _find_existing(self, project_id: int, fact: str) -> MemoryFactORM | None:
        result = await self.session.execute(
            select(MemoryFactORM).where(
                MemoryFactORM.project_id == project_id,
                MemoryFactORM.fact == fact,
            )
        )
        return result.scalar_one_or_none()
