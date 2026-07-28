import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import TypedArtifactType
from localforge.storage.orm import TypedHandoffArtifactORM

logger = logging.getLogger(__name__)


def compute_artifact_hash(
    summary: str,
    evidence: dict[str, Any],
    changed_files: list[str],
    tests_executed: list[str],
    validation_results: dict[str, Any],
) -> str:
    """Compute deterministic SHA-256 hash over canonical JSON artifact payload."""
    payload = {
        "summary": summary,
        "evidence": evidence,
        "changed_files": sorted(changed_files),
        "tests_executed": sorted(tests_executed),
        "validation_results": validation_results,
    }
    canonical_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


class TypedHandoffService:
    """Service layer managing typed, evidence-carrying handoff artifacts and DAG provenance verification."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_artifact(
        self,
        project_id: int,
        task_run_id: int,
        producer_agent_id: str,
        consumer_agent_id: str,
        summary: str,
        artifact_type: TypedArtifactType = TypedArtifactType.RESEARCH,
        schema_version: str = "1.0",
        evidence_json: dict[str, Any] | None = None,
        changed_files: list[str] | None = None,
        tests_executed: list[str] | None = None,
        validation_results_json: dict[str, Any] | None = None,
        open_questions: list[str] | None = None,
        risks: list[str] | None = None,
        not_checked: list[str] | None = None,
    ) -> domain.TypedHandoffArtifact:
        """Create and persist a new validated TypedHandoffArtifact with SHA-256 content_hash."""
        ev = evidence_json or {}
        cf = changed_files or []
        te = tests_executed or []
        vr = validation_results_json or {}

        c_hash = compute_artifact_hash(summary, ev, cf, te, vr)

        artifact = domain.TypedHandoffArtifact(
            project_id=project_id,
            task_run_id=task_run_id,
            producer_agent_id=producer_agent_id,
            consumer_agent_id=consumer_agent_id,
            artifact_type=artifact_type,
            schema_version=schema_version,
            summary=summary,
            evidence_json=ev,
            changed_files=cf,
            tests_executed=te,
            validation_results_json=vr,
            open_questions=open_questions or [],
            risks=risks or [],
            not_checked=not_checked or [],
            content_hash=c_hash,
            is_consumed=False,
        )

        orm_obj = TypedHandoffArtifactORM.from_domain(artifact)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def validate_artifact_integrity(self, artifact_id: int) -> tuple[bool, str | None]:
        """Validate content_hash against the actual payload data stored in the artifact."""
        stmt = select(TypedHandoffArtifactORM).where(TypedHandoffArtifactORM.id == artifact_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            return False, f"Artifact ID {artifact_id} not found."

        art = orm_obj.to_domain()
        expected_hash = compute_artifact_hash(
            art.summary,
            art.evidence_json,
            art.changed_files,
            art.tests_executed,
            art.validation_results_json,
        )

        if art.content_hash != expected_hash:
            msg = f"Tampered artifact detected! Stored hash '{art.content_hash}' does not match computed '{expected_hash}'."
            logger.error(msg)
            return False, msg

        return True, None

    async def consume_artifact(self, artifact_id: int) -> domain.TypedHandoffArtifact:
        """Enforce consume-once semantics for specified handoff artifacts."""
        stmt = select(TypedHandoffArtifactORM).where(TypedHandoffArtifactORM.id == artifact_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Artifact ID {artifact_id} not found.")

        if orm_obj.is_consumed:
            raise ValueError(f"Artifact ID {artifact_id} has already been consumed.")

        orm_obj.is_consumed = True
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_artifacts_for_run(self, task_run_id: int) -> list[domain.TypedHandoffArtifact]:
        """List all typed handoff artifacts produced during a task run."""
        stmt = (
            select(TypedHandoffArtifactORM)
            .where(TypedHandoffArtifactORM.task_run_id == task_run_id)
            .order_by(TypedHandoffArtifactORM.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    def render_markdown_summary(self, artifact: domain.TypedHandoffArtifact) -> str:
        """Render a human-readable Markdown report with alerts for risks and unresolved questions."""
        lines = [
            f"# Typed Handoff Artifact: {artifact.artifact_type.value}",
            f"- **Schema Version**: {artifact.schema_version}",
            f"- **Producer Agent**: `{artifact.producer_agent_id}`",
            f"- **Consumer Agent**: `{artifact.consumer_agent_id}`",
            f"- **Content Hash**: `{artifact.content_hash[:16]}...`",
            "",
            "## Summary",
            self._redact_secrets(artifact.summary),
            "",
        ]

        if artifact.changed_files:
            lines.append("## Changed Files")
            for f in artifact.changed_files:
                lines.append(f"- `{f}`")
            lines.append("")

        if artifact.tests_executed:
            lines.append("## Tests Executed")
            for t in artifact.tests_executed:
                lines.append(f"- `{t}`")
            lines.append("")

        if artifact.risks:
            lines.append("> [!WARNING]")
            lines.append("> **Identified Risks**:")
            for r in artifact.risks:
                lines.append(f"> - {self._redact_secrets(r)}")
            lines.append("")

        if artifact.open_questions:
            lines.append("> [!IMPORTANT]")
            lines.append("> **Open Questions**:")
            for q in artifact.open_questions:
                lines.append(f"> - {self._redact_secrets(q)}")
            lines.append("")

        if artifact.not_checked:
            lines.append("> [!NOTE]")
            lines.append("> **Not Checked Items**:")
            for nc in artifact.not_checked:
                lines.append(f"> - {self._redact_secrets(nc)}")
            lines.append("")

        return "\n".join(lines)

    def _redact_secrets(self, text: str) -> str:
        """Redact sensitive token strings or API key patterns."""
        redacted = re.sub(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[\w\-]+['\"]?", r"\1: [REDACTED]", text)
        return redacted
