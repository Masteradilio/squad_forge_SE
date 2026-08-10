"""Shared application services for the DeepCode-inspired ForgeOS capabilities.

The services in this module are deliberately deterministic at their boundary:
model discovery is delegated to OmniRoute, Skills are snapshotted by digest,
and an AutomationRun records the exact continuity turn it admitted.  API, CLI,
and benchmark callers use these same services.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain, enums
from localforge.services.engineering import EngineeringNotFound
from localforge.services.omniroute_client import OmniRouteClient
from localforge.services.tenant_context import current_context
from localforge.skills.registry import SkillDefinition
from localforge.storage.orm import (
    AutomationORM,
    AutomationRunORM,
    EngineeringTurnORM,
    ModelCatalogEntryORM,
    ModelConnectionORM,
    ModelVerificationORM,
    ProjectORM,
    SkillBindingORM,
)


class DeepCodeCapabilityError(RuntimeError):
    """Raised when a capability cannot be admitted under ForgeOS policy."""


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_error(value: Any) -> str:
    text = str(value)
    text = re.sub(r"(?i)(api[-_ ]?key|authorization|token|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"Bearer\s+[^\s]+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    return text[:1000]


class _TenantProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @property
    def tenant_id(self) -> str:
        return current_context().tenant_id

    async def project(self, project_id: int) -> ProjectORM:
        result = await self.session.execute(
            select(ProjectORM).where(
                ProjectORM.id == project_id,
                ProjectORM.tenant_id == self.tenant_id,
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise EngineeringNotFound("Project not found for current tenant")
        return project


class ModelCatalogService(_TenantProjectService):
    """Persist OmniRoute model discovery and verification evidence."""

    def __init__(
        self,
        session: AsyncSession,
        client_factory: Callable[[], OmniRouteClient] | None = None,
    ):
        super().__init__(session)
        self._client_factory = client_factory or OmniRouteClient

    @staticmethod
    def _endpoint_ref() -> str:
        # The concrete gateway URL and credentials remain process configuration,
        # never durable product data.
        return "omniroute://configured-gateway"

    async def _connection(self, project_id: int) -> ModelConnectionORM:
        project = await self.project(project_id)
        result = await self.session.execute(
            select(ModelConnectionORM).where(
                ModelConnectionORM.project_id == project.id,
                ModelConnectionORM.tenant_id == project.tenant_id,
                ModelConnectionORM.provider == "omniroute",
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            connection = ModelConnectionORM(
                id=_uid("conn"),
                project_id=project.id,
                tenant_id=project.tenant_id,
                provider="omniroute",
                endpoint_ref=self._endpoint_ref(),
                credential_ref="env:OMNIROUTE_API_KEY",
                status=enums.ModelVerificationStatus.PENDING.value,
            )
            self.session.add(connection)
            await self.session.flush()
        return connection

    async def discover(self, project_id: int) -> list[domain.ModelCatalogEntry]:
        connection = await self._connection(project_id)
        client = self._client_factory()
        try:
            models = await client.get_models()
            if not isinstance(models, list):
                raise DeepCodeCapabilityError("OmniRoute catalog response was not a list")
            now = _now()
            connection.status = enums.ModelVerificationStatus.VERIFIED.value if models else enums.ModelVerificationStatus.FAILED.value
            connection.verified_at = now
            connection.capabilities_json = {"model_count": len(models), "source": "omniroute"}
            connection.sanitized_error = None if models else "OmniRoute catalog returned no models"
            entries: list[domain.ModelCatalogEntry] = []
            for item in models:
                if isinstance(item, str):
                    name, metadata = item, {}
                elif isinstance(item, dict):
                    name = str(item.get("id") or item.get("name") or "").strip()
                    metadata = {str(k): v for k, v in item.items() if k not in {"api_key", "authorization", "token"}}
                else:
                    continue
                if not name:
                    continue
                existing_result = await self.session.execute(
                    select(ModelCatalogEntryORM).where(
                        ModelCatalogEntryORM.connection_id == connection.id,
                        ModelCatalogEntryORM.model_name == name,
                        ModelCatalogEntryORM.tenant_id == connection.tenant_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()
                if existing is None:
                    existing = ModelCatalogEntryORM(
                        id=_uid("model"),
                        connection_id=connection.id,
                        project_id=connection.project_id,
                        tenant_id=connection.tenant_id,
                        provider="omniroute",
                        model_name=name,
                        status=enums.ModelVerificationStatus.DISCOVERED.value,
                        endpoint_ref=connection.endpoint_ref,
                    )
                    self.session.add(existing)
                existing.status = enums.ModelVerificationStatus.DISCOVERED.value
                existing.metadata_json = metadata
                existing.capabilities_json = metadata.get("capabilities", {}) if isinstance(metadata, dict) else {}
                existing.verified_at = now
                existing.sanitized_error = None
                await self.session.flush()
                entries.append(existing.to_domain())
            self.session.add(
                ModelVerificationORM(
                    id=_uid("verify"),
                    connection_id=connection.id,
                    project_id=connection.project_id,
                    tenant_id=connection.tenant_id,
                    provider="omniroute",
                    status=connection.status,
                    capabilities_json=dict(connection.capabilities_json or {}),
                    verified_at=connection.verified_at,
                    sanitized_error=connection.sanitized_error,
                    endpoint_ref=connection.endpoint_ref,
                )
            )
            await self.session.flush()
            return entries
        except Exception as exc:
            connection.status = enums.ModelVerificationStatus.FAILED.value
            connection.verified_at = _now()
            connection.sanitized_error = _safe_error(exc)
            self.session.add(
                ModelVerificationORM(
                    id=_uid("verify"),
                    connection_id=connection.id,
                    project_id=connection.project_id,
                    tenant_id=connection.tenant_id,
                    provider="omniroute",
                    status=connection.status,
                    sanitized_error=connection.sanitized_error,
                    endpoint_ref=connection.endpoint_ref,
                )
            )
            await self.session.flush()
            # The failed attempt is durable evidence; callers can inspect the
            # verification endpoint instead of mistaking an empty list for a
            # healthy empty catalog.
            return []

    async def probe(self, project_id: int, model_name: str) -> domain.ModelVerification:
        connection = await self._connection(project_id)
        entry_result = await self.session.execute(
            select(ModelCatalogEntryORM).where(
                ModelCatalogEntryORM.connection_id == connection.id,
                ModelCatalogEntryORM.model_name == model_name,
                ModelCatalogEntryORM.tenant_id == connection.tenant_id,
            )
        )
        entry = entry_result.scalar_one_or_none()
        if entry is None:
            raise DeepCodeCapabilityError("Model is not present in the OmniRoute catalog")
        status = enums.ModelVerificationStatus.VERIFIED
        capabilities: dict[str, Any] = {}
        error: str | None = None
        try:
            client = self._client_factory()
            ok = await client.verify_json_contract(model_name)
            capabilities["json_contract"] = bool(ok)
            if not ok:
                status = enums.ModelVerificationStatus.FAILED
                error = "OmniRoute JSON contract probe failed"
        except TimeoutError as exc:
            status, error = enums.ModelVerificationStatus.TIMEOUT, _safe_error(exc)
        except Exception as exc:
            status, error = enums.ModelVerificationStatus.FAILED, _safe_error(exc)
        verified_at = _now()
        entry.status = status.value
        entry.capabilities_json = capabilities
        entry.verified_at = verified_at
        entry.sanitized_error = error
        verification = ModelVerificationORM(
            id=_uid("verify"),
            connection_id=connection.id,
            catalog_entry_id=entry.id,
            project_id=connection.project_id,
            tenant_id=connection.tenant_id,
            provider="omniroute",
            model_name=model_name,
            status=status.value,
            capabilities_json=capabilities,
            verified_at=verified_at,
            sanitized_error=error,
            endpoint_ref=connection.endpoint_ref,
        )
        self.session.add(verification)
        await self.session.flush()
        return verification.to_domain()

    async def list_entries(self, project_id: int) -> list[domain.ModelCatalogEntry]:
        await self.project(project_id)
        result = await self.session.execute(
            select(ModelCatalogEntryORM)
            .where(
                ModelCatalogEntryORM.project_id == project_id,
                ModelCatalogEntryORM.tenant_id == self.tenant_id,
            )
            .order_by(ModelCatalogEntryORM.model_name)
        )
        return [row.to_domain() for row in result.scalars().all()]

    async def list_verifications(self, project_id: int) -> list[domain.ModelVerification]:
        await self.project(project_id)
        result = await self.session.execute(
            select(ModelVerificationORM)
            .where(
                ModelVerificationORM.project_id == project_id,
                ModelVerificationORM.tenant_id == self.tenant_id,
            )
            .order_by(ModelVerificationORM.created_at.desc())
        )
        return [row.to_domain() for row in result.scalars().all()]


class SkillBindingService(_TenantProjectService):
    async def bind(
        self,
        *,
        project_id: int,
        session_id: str,
        turn_id: str,
        skill: SkillDefinition | dict[str, Any] | str,
        origin: str | None = None,
    ) -> domain.SkillBinding:
        project = await self.project(project_id)
        turn_result = await self.session.execute(
            select(EngineeringTurnORM).where(
                EngineeringTurnORM.id == turn_id,
                EngineeringTurnORM.session_id == session_id,
                EngineeringTurnORM.project_id == project_id,
                EngineeringTurnORM.tenant_id == project.tenant_id,
            )
        )
        turn = turn_result.scalar_one_or_none()
        if turn is None:
            raise EngineeringNotFound("Engineering turn not found for current tenant/project")
        if isinstance(skill, SkillDefinition):
            definition = skill
        else:
            definition = SkillDefinition.model_validate(skill) if isinstance(skill, dict) else SkillDefinition(name=skill, purpose="registry skill")
        manifest = definition.model_dump(mode="json")
        digest = _json_hash(manifest)
        binding = domain.SkillBinding(
            id=_uid("skillbind"),
            project_id=project_id,
            tenant_id=project.tenant_id,
            session_id=session_id,
            turn_id=turn_id,
            name=definition.name,
            version=definition.manifest_version,
            digest=digest,
            origin=origin or definition.source,
            manifest_snapshot=manifest,
        )
        self.session.add(SkillBindingORM.from_domain(binding))
        await self.session.flush()
        return binding

    async def list(self, project_id: int, *, session_id: str | None = None, turn_id: str | None = None) -> list[domain.SkillBinding]:
        await self.project(project_id)
        stmt = select(SkillBindingORM).where(SkillBindingORM.project_id == project_id, SkillBindingORM.tenant_id == self.tenant_id)
        if session_id:
            stmt = stmt.where(SkillBindingORM.session_id == session_id)
        if turn_id:
            stmt = stmt.where(SkillBindingORM.turn_id == turn_id)
        result = await self.session.execute(stmt.order_by(SkillBindingORM.created_at.asc()))
        return [row.to_domain() for row in result.scalars().all()]


class AutomationService(_TenantProjectService):
    async def create(self, automation: domain.Automation) -> domain.Automation:
        project = await self.project(automation.project_id)
        if automation.trigger_kind.upper() == "INTERVAL" and not automation.interval_seconds:
            raise DeepCodeCapabilityError("Interval automations require interval_seconds")
        automation = automation.model_copy(update={"tenant_id": project.tenant_id, "id": automation.id or _uid("auto")})
        self.session.add(AutomationORM.from_domain(automation))
        await self.session.flush()
        return automation

    async def get(self, automation_id: str) -> domain.Automation:
        result = await self.session.execute(select(AutomationORM).where(AutomationORM.id == automation_id, AutomationORM.tenant_id == self.tenant_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise EngineeringNotFound("Automation not found")
        return row.to_domain()

    async def list(self, project_id: int) -> list[domain.Automation]:
        await self.project(project_id)
        result = await self.session.execute(
            select(AutomationORM)
            .where(AutomationORM.project_id == project_id, AutomationORM.tenant_id == self.tenant_id)
            .order_by(AutomationORM.created_at.asc())
        )
        return [row.to_domain() for row in result.scalars().all()]

    async def set_status(self, automation_id: str, status: enums.AutomationStatus) -> domain.Automation:
        result = await self.session.execute(select(AutomationORM).where(AutomationORM.id == automation_id, AutomationORM.tenant_id == self.tenant_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise EngineeringNotFound("Automation not found")
        row.status = status.value
        await self.session.flush()
        return row.to_domain()

    async def trigger(self, automation_id: str, idempotency_key: str) -> domain.AutomationRun:
        automation = await self.get(automation_id)
        existing_result = await self.session.execute(
            select(AutomationRunORM).where(
                AutomationRunORM.automation_id == automation.id,
                AutomationRunORM.idempotency_key == idempotency_key,
                AutomationRunORM.tenant_id == self.tenant_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing.to_domain()
        if automation.status != enums.AutomationStatus.ACTIVE:
            raise DeepCodeCapabilityError(f"Automation is {automation.status.value.lower()}")
        if automation.active_run_id:
            raise DeepCodeCapabilityError("Automation already has an active run")
        run = domain.AutomationRun(
            id=_uid("autorun"),
            automation_id=automation.id or "",
            project_id=automation.project_id,
            tenant_id=automation.tenant_id,
            trigger_kind=automation.trigger_kind,
            idempotency_key=idempotency_key,
            goal_snapshot=automation.goal_template,
            profile_snapshot=automation.profile_snapshot,
            budget_snapshot=automation.budgets,
            evidence={"execution": "shared-engineering-runtime"},
        )
        run = run.model_copy(update={"status": enums.AutomationRunStatus.RUNNING})
        self.session.add(AutomationRunORM.from_domain(run))
        automation_row_result = await self.session.execute(
            select(AutomationORM).where(AutomationORM.id == automation.id, AutomationORM.tenant_id == self.tenant_id)
        )
        automation_row = automation_row_result.scalar_one()
        automation_row.active_run_id = run.id
        await self.session.flush()
        try:
            from localforge.services.engineering import EngineeringContinuityService

            engineering = EngineeringContinuityService(self.session)
            session_id = automation.session_id
            if not session_id:
                session = await engineering.create_session(project_id=automation.project_id, title=f"Automation: {automation.name}")
                session_id = session.id
            objective = str(automation.goal_template.get("objective") or automation.goal_template.get("instruction") or automation.name)
            goal = await engineering.create_goal(
                session_id=session_id, objective=objective, acceptance_criteria=list(automation.goal_template.get("acceptance_criteria", []))
            )
            turn = await engineering.admit_turn(session_id=session_id, input_text=objective, idempotency_key=f"{idempotency_key}:turn")
            run = run.model_copy(
                update={
                    "status": enums.AutomationRunStatus.COMPLETED,
                    "session_id": session_id,
                    "turn_id": turn.id,
                    "completed_at": _now(),
                    "evidence": {"execution": "shared-engineering-runtime", "goal_id": goal.id, "turn_id": turn.id},
                }
            )
            automation_row.active_run_id = None
            automation_row.next_run_at = _now() if automation.trigger_kind.upper() == "INTERVAL" else None
            existing_row = await self.session.get(AutomationRunORM, run.id)
            if existing_row is not None:
                for key, value in AutomationRunORM.from_domain(run).__dict__.items():
                    if not key.startswith("_") and key not in {"id", "automation_id", "project_id", "tenant_id", "created_at"}:
                        setattr(existing_row, key, value)
            await self.session.flush()
            return run
        except Exception as exc:
            automation_row.active_run_id = None
            row = await self.session.get(AutomationRunORM, run.id)
            if row is not None:
                row.status = enums.AutomationRunStatus.FAILED.value
                row.error_message = _safe_error(exc)
                row.completed_at = _now()
            await self.session.flush()
            raise

    async def list_runs(self, automation_id: str) -> list[domain.AutomationRun]:
        await self.get(automation_id)
        result = await self.session.execute(
            select(AutomationRunORM)
            .where(AutomationRunORM.automation_id == automation_id, AutomationRunORM.tenant_id == self.tenant_id)
            .order_by(AutomationRunORM.created_at.desc())
        )
        return [row.to_domain() for row in result.scalars().all()]
