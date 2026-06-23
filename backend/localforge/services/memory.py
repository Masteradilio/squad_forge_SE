import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import ArtifactType, MemoryRecordKind
from localforge.storage.orm import MemoryFactORM


class MemoryService:
    """Persist project memory facts and backup snapshots."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_facts(self, project_id: int) -> list[domain.MemoryFact]:
        result = await self.session.execute(
            select(MemoryFactORM)
            .where(MemoryFactORM.project_id == project_id)
            .order_by(MemoryFactORM.pinned.desc(), MemoryFactORM.updated_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def create_fact(self, fact: domain.MemoryFact) -> domain.MemoryFact:
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

    async def export_backup(self, project_id: int, *, fmt: str = "json") -> str:
        payload = {
            "project_id": project_id,
            "facts": [
                fact.model_dump(mode="json") for fact in await self.list_facts(project_id)
            ],
        }
        if fmt == "json":
            return json.dumps(payload, indent=2, sort_keys=True)
        if fmt == "yaml":
            return _render_simple_yaml(payload)
        raise ValueError("Unsupported memory export format")

    async def import_backup(self, project_id: int, payload: dict[str, Any]) -> list[domain.MemoryFact]:
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

    async def retrieve_relevant(
        self, project_id: int, *, query: str, limit: int = 5
    ) -> list[domain.MemoryFact]:
        facts = [fact for fact in await self.list_facts(project_id) if fact.status == "active"]
        query_terms = _terms(query)
        scored: list[tuple[int, domain.MemoryFact]] = []
        for fact in facts:
            haystack = " ".join([fact.fact, fact.kind.value, " ".join(fact.tags)]).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if fact.pinned:
                score += 2
            if score > 0:
                scored.append((score, fact))
        scored.sort(key=lambda item: (-item[0], item[1].updated_at), reverse=False)
        return [fact for _, fact in scored[:limit]]

    async def learn_from_completed_run(
        self,
        *,
        project_id: int,
        task_key: str,
        task_title: str,
        final_summary: str | None,
        artifact_summaries: list[tuple[ArtifactType, str | None]],
    ) -> list[domain.MemoryFact]:
        learned: list[domain.MemoryFact] = []
        if final_summary:
            learned.append(
                await self.create_fact(
                    domain.MemoryFact(
                        project_id=project_id,
                        kind=MemoryRecordKind.RESOLVED_BLOCKER,
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
            elif artifact_type in {ArtifactType.RISK, ArtifactType.BLOCKER}:
                kind = MemoryRecordKind.KNOWN_PITFALL
            else:
                continue
            learned.append(
                await self.create_fact(
                    domain.MemoryFact(
                        project_id=project_id,
                        kind=kind,
                        fact=f"{task_key} {artifact_type.value}: {summary[:240]}",
                        source="completed_run",
                        tags=[task_key, artifact_type.value],
                    )
                )
            )
        return learned

    async def _find_existing(self, project_id: int, fact: str) -> MemoryFactORM | None:
        result = await self.session.execute(
            select(MemoryFactORM).where(
                MemoryFactORM.project_id == project_id,
                MemoryFactORM.fact == fact,
            )
        )
        return result.scalar_one_or_none()


def _render_simple_yaml(payload: dict[str, Any]) -> str:
    lines = [f"project_id: {payload['project_id']}", "facts:"]
    for fact in payload["facts"]:
        lines.extend(
            [
                f"  - id: {fact.get('id')}",
                f"    kind: {json.dumps(fact.get('kind', 'stack_fact'))}",
                f"    fact: {json.dumps(fact.get('fact', ''))}",
                f"    source: {json.dumps(fact.get('source', 'manual'))}",
                f"    pinned: {str(bool(fact.get('pinned'))).lower()}",
                f"    status: {json.dumps(fact.get('status', 'active'))}",
                "    tags:",
            ]
        )
        for tag in fact.get("tags", []):
            lines.append(f"      - {json.dumps(tag)}")
    return "\n".join(lines) + "\n"


def _terms(text: str) -> set[str]:
    return {part.lower() for part in text.replace("-", " ").replace("_", " ").split() if len(part) > 2}
