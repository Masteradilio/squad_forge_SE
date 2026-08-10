"""Reference ingestion, lexical CodeRAG, citations, and ProductBlueprints."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.services.engineering import EngineeringNotFound
from localforge.services.security_controls import redact_secrets
from localforge.services.tenant_context import current_context
from localforge.storage.orm import (
    DocumentChunkORM,
    ProductBlueprintORM,
    ProjectORM,
    ReferenceDecisionORM,
    ReferenceSourceORM,
)


class ReferenceContinuityError(RuntimeError):
    pass


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\wÀ-ÿ]{3,}", value.casefold())}


_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+prompt",
    r"developer\s+message",
    r"do\s+not\s+follow",
    r"reveal\s+secrets",
)


class ReferenceContinuityService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @property
    def tenant_id(self) -> str:
        return current_context().tenant_id

    async def _project(self, project_id: int) -> ProjectORM:
        result = await self.session.execute(select(ProjectORM).where(ProjectORM.id == project_id, ProjectORM.tenant_id == self.tenant_id))
        project = result.scalar_one_or_none()
        if project is None:
            raise EngineeringNotFound("Project not found for current tenant")
        return project

    async def ingest_text(
        self,
        *,
        project_id: int,
        name: str,
        content: str,
        source_type: str = "markdown",
        path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> domain.ReferenceSource:
        project = await self._project(project_id)
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        redacted = redact_secrets(normalized)
        redaction_status = "REDACTED" if redacted != normalized else "NOT_REQUIRED"
        injection = "QUARANTINED" if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _INJECTION_PATTERNS) else "CLEAN"
        source_metadata = {**(metadata or {}), "provenance": {"pipeline": "reference-continuity", "external_untrusted": source_type == "context7"}}
        source = domain.ReferenceSource(
            id=_uid("source"),
            project_id=project_id,
            tenant_id=project.tenant_id,
            name=name,
            source_type=source_type,
            path=path,
            content_hash=_sha(redacted),
            normalized_text=redacted,
            injection_status=injection,
            redaction_status=redaction_status,
            metadata=source_metadata,
        )
        existing_result = await self.session.execute(
            select(ReferenceSourceORM).where(
                ReferenceSourceORM.project_id == project_id,
                ReferenceSourceORM.tenant_id == project.tenant_id,
                ReferenceSourceORM.content_hash == source.content_hash,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing.to_domain()
        self.session.add(ReferenceSourceORM.from_domain(source))
        await self.session.flush()
        await self._chunk_source(source)
        try:
            from localforge.memory.mempalace_service import MemPalaceService

            memory_path = MemPalaceService(Path(project.root_path) / ".localforge" / "mempalace").save_loci_memory(
                str(project.id),
                "references",
                {"tenant_id": project.tenant_id, "source_id": source.id, "content_hash": source.content_hash, "injection_status": source.injection_status},
            )
            source.metadata["mempalace_path"] = memory_path
            source_row = await self.session.get(ReferenceSourceORM, source.id)
            if source_row is not None:
                source_row.metadata_json = dict(source.metadata)
                await self.session.flush()
        except (OSError, ValueError):
            pass
        return source

    async def ingest_context7_excerpt(self, *, project_id: int, name: str, content: str, library: str) -> domain.ReferenceSource:
        """Normalize an external Context7 excerpt into the citation model."""
        return await self.ingest_text(
            project_id=project_id,
            name=name,
            content=content,
            source_type="context7",
            metadata={"library": library, "external_untrusted": True},
        )

    async def ingest_file(self, *, project_id: int, path: str, source_type: str = "markdown") -> domain.ReferenceSource:
        project = await self._project(project_id)
        resolved = Path(path).expanduser().resolve()
        try:
            resolved.relative_to(Path(project.root_path).expanduser().resolve())
        except ValueError as exc:
            raise ReferenceContinuityError("Reference path must remain inside project root") from exc
        return await self.ingest_text(
            project_id=project_id, name=resolved.name, content=resolved.read_text(encoding="utf-8"), source_type=source_type, path=str(resolved)
        )

    async def _chunk_source(self, source: domain.ReferenceSource) -> None:
        lines = source.normalized_text.splitlines() or [""]
        current_section: str | None = None
        buffer: list[str] = []
        start_line = 1
        ordinal = 0

        async def flush(end_line: int) -> None:
            nonlocal buffer, start_line, ordinal
            text = "\n".join(buffer).strip()
            if not text:
                return
            chunk = domain.DocumentChunk(
                id=_uid("chunk"),
                source_id=source.id or "",
                project_id=source.project_id,
                tenant_id=source.tenant_id,
                ordinal=ordinal,
                text=text,
                section=current_section,
                line_start=start_line,
                line_end=end_line,
                content_hash=_sha(text),
                metadata={"injection_status": source.injection_status},
            )
            self.session.add(DocumentChunkORM.from_domain(chunk))
            ordinal += 1
            buffer = []

        for index, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                await flush(index - 1)
                current_section = line.lstrip("# ").strip()[:255] or current_section
                start_line = index
            buffer.append(line)
            if len("\n".join(buffer)) >= 1400:
                await flush(index)
                start_line = index + 1
        await flush(len(lines))
        await self.session.flush()

    async def list_sources(self, project_id: int) -> list[domain.ReferenceSource]:
        await self._project(project_id)
        result = await self.session.execute(
            select(ReferenceSourceORM)
            .where(ReferenceSourceORM.project_id == project_id, ReferenceSourceORM.tenant_id == self.tenant_id)
            .order_by(ReferenceSourceORM.created_at.asc())
        )
        return [row.to_domain() for row in result.scalars().all()]

    async def search(self, *, project_id: int, query: str, limit: int = 8) -> list[dict[str, Any]]:
        await self._project(project_id)
        terms = _tokens(query)
        if not terms:
            return []
        result = await self.session.execute(
            select(DocumentChunkORM).where(DocumentChunkORM.project_id == project_id, DocumentChunkORM.tenant_id == self.tenant_id)
        )
        scored: list[tuple[float, DocumentChunkORM]] = []
        for chunk in result.scalars().all():
            source_result = await self.session.execute(
                select(ReferenceSourceORM.injection_status).where(ReferenceSourceORM.id == chunk.source_id, ReferenceSourceORM.tenant_id == self.tenant_id)
            )
            injection_status = source_result.scalar_one_or_none()
            if injection_status == "QUARANTINED":
                continue
            overlap = len(terms & _tokens(chunk.text))
            if overlap:
                score = overlap / max(1, len(terms))
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].ordinal))
        return [
            {
                "chunk_id": chunk.id,
                "source_id": chunk.source_id,
                "score": round(score, 6),
                "text": chunk.text,
                "section": chunk.section,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "citation": f"{chunk.source_id}#L{chunk.line_start}-L{chunk.line_end}",
                "content_hash": chunk.content_hash,
            }
            for score, chunk in scored[: max(1, min(limit, 50))]
        ]

    async def decide(
        self,
        *,
        project_id: int,
        query: str,
        summary: str,
        selected_chunk_ids: list[str],
        turn_id: str | None = None,
        decision: str = "APPROVED",
    ) -> domain.ReferenceDecision:
        project = await self._project(project_id)
        result = await self.session.execute(
            select(DocumentChunkORM).where(
                DocumentChunkORM.project_id == project_id, DocumentChunkORM.tenant_id == project.tenant_id, DocumentChunkORM.id.in_(selected_chunk_ids)
            )
        )
        chunks = list(result.scalars().all())
        if len(chunks) != len(set(selected_chunk_ids)):
            raise ReferenceContinuityError("One or more selected chunks are not available to this tenant/project")
        citations = [
            {
                "chunk_id": chunk.id,
                "source_id": chunk.source_id,
                "section": chunk.section,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "content_hash": chunk.content_hash,
            }
            for chunk in chunks
        ]
        payload = {"query": query, "summary": summary, "selected_chunk_ids": selected_chunk_ids, "citations": citations, "decision": decision}
        reference = domain.ReferenceDecision(
            id=_uid("decision"),
            project_id=project_id,
            tenant_id=project.tenant_id,
            query=query,
            selected_chunk_ids=selected_chunk_ids,
            citations=citations,
            summary=summary,
            decision=decision,
            turn_id=turn_id,
            content_hash=_sha(str(payload)),
        )
        self.session.add(ReferenceDecisionORM.from_domain(reference))
        await self.session.flush()
        return reference

    async def build_blueprint(self, *, project_id: int, name: str, decision_id: str, freeze: bool = True) -> domain.ProductBlueprint:
        project = await self._project(project_id)
        result = await self.session.execute(
            select(ReferenceDecisionORM).where(
                ReferenceDecisionORM.id == decision_id, ReferenceDecisionORM.project_id == project_id, ReferenceDecisionORM.tenant_id == project.tenant_id
            )
        )
        decision = result.scalar_one_or_none()
        if decision is None:
            raise EngineeringNotFound("Reference decision not found")
        citations = list(decision.citations_json or [])
        chunks_result = await self.session.execute(
            select(DocumentChunkORM).where(
                DocumentChunkORM.id.in_(decision.selected_chunk_ids_json),
                DocumentChunkORM.project_id == project_id,
                DocumentChunkORM.tenant_id == project.tenant_id,
            )
        )
        text = "\n".join(chunk.text for chunk in chunks_result.scalars().all())
        headings = [line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")]
        criteria = [line.lstrip("- ").strip() for line in text.splitlines() if "accept" in line.casefold() or "must" in line.casefold()]
        blueprint_payload = {
            "name": name,
            "summary": decision.summary,
            "modules": [{"name": heading} for heading in headings],
            "acceptance_criteria": criteria[:20],
            "citation_ids": [str(item.get("chunk_id")) for item in citations],
        }
        try:
            from localforge.memory.graphify_engine import GraphifyEngine

            graph = GraphifyEngine(Path(project.root_path)).build_codebase_graph()
            blueprint_payload["modules"].append({"name": "existing-codebase", "graph_nodes": graph.get("nodes_count", 0)})
        except (OSError, ValueError, SyntaxError):
            pass
        blueprint = domain.ProductBlueprint(
            id=_uid("blueprint"),
            project_id=project_id,
            tenant_id=project.tenant_id,
            name=name,
            summary=decision.summary,
            modules=blueprint_payload["modules"],
            acceptance_criteria=criteria[:20],
            citation_ids=blueprint_payload["citation_ids"],
            source_hashes=[str(item.get("content_hash")) for item in citations],
            status="FROZEN" if freeze else "DRAFT",
            content_hash=_sha(str(blueprint_payload)),
            frozen_at=datetime.now(UTC) if freeze else None,
        )
        self.session.add(ProductBlueprintORM.from_domain(blueprint))
        await self.session.flush()
        return blueprint

    async def get_blueprint(self, project_id: int, blueprint_id: str) -> domain.ProductBlueprint:
        project = await self._project(project_id)
        result = await self.session.execute(
            select(ProductBlueprintORM).where(
                ProductBlueprintORM.id == blueprint_id, ProductBlueprintORM.project_id == project_id, ProductBlueprintORM.tenant_id == project.tenant_id
            )
        )
        blueprint = result.scalar_one_or_none()
        if blueprint is None:
            raise EngineeringNotFound("Product blueprint not found")
        return blueprint.to_domain()
