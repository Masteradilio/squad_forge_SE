"""API routes for OmniRoute catalog, Skill bindings, and Automations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import (
    AutomationCreateRequest,
    AutomationTriggerRequest,
    ModelProbeRequest,
    SkillBindingRequest,
)
from localforge.models import domain
from localforge.models.enums import AutomationStatus
from localforge.services.deepcode_capabilities import (
    DeepCodeCapabilityError,
)
from localforge.services.operational_profiles import (
    available_profile_manifest,
    profile_manifest,
)
from localforge.storage import DatabaseManager, UnitOfWork


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _http(exc: Exception) -> None:
    if isinstance(exc, DeepCodeCapabilityError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def create_capabilities_router(manager: DatabaseManager) -> APIRouter:
    router = APIRouter(tags=["deepcode-capabilities"])

    @router.get("/capabilities/operational-profiles")
    async def operational_profiles() -> dict[str, Any]:
        """List governed local, release and optional SaaS capabilities."""

        return available_profile_manifest()

    @router.get("/projects/{project_id}/operational-profiles")
    async def project_operational_profiles(project_id: int) -> dict[str, Any]:
        """Expose the same profile registry under a project-scoped boundary."""

        # Project scoping is intentionally represented in the response while
        # profile definitions remain immutable and tenant-neutral.
        return {"project_id": project_id, **profile_manifest(["reference", "saas", "full_coverage"])}

    @router.get("/projects/{project_id}/models/catalog")
    async def model_catalog(project_id: int) -> list[dict[str, Any]]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.model_catalog is not None
                return [_dump(item) for item in await uow.model_catalog.list_entries(project_id)]
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.post("/projects/{project_id}/models/catalog/discover")
    async def discover_models(project_id: int) -> list[dict[str, Any]]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.model_catalog is not None
                return [_dump(item) for item in await uow.model_catalog.discover(project_id)]
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.post("/projects/{project_id}/models/catalog/probe")
    async def probe_model(project_id: int, req: ModelProbeRequest) -> dict[str, Any]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.model_catalog is not None
                return _dump(await uow.model_catalog.probe(project_id, req.model_name))
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.get("/projects/{project_id}/models/verifications")
    async def model_verifications(project_id: int) -> list[dict[str, Any]]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.model_catalog is not None
                return [_dump(item) for item in await uow.model_catalog.list_verifications(project_id)]
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.post("/projects/{project_id}/engineering/skill-bindings", status_code=status.HTTP_201_CREATED)
    async def bind_skill(project_id: int, req: SkillBindingRequest) -> dict[str, Any]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.skill_bindings is not None
                return _dump(
                    await uow.skill_bindings.bind(
                        project_id=project_id,
                        session_id=req.session_id,
                        turn_id=req.turn_id,
                        skill=req.skill,
                        origin=req.origin,
                    )
                )
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.get("/projects/{project_id}/engineering/skill-bindings")
    async def list_skill_bindings(project_id: int, session_id: str | None = None, turn_id: str | None = None) -> list[dict[str, Any]]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.skill_bindings is not None
                return [_dump(item) for item in await uow.skill_bindings.list(project_id, session_id=session_id, turn_id=turn_id)]
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.post("/projects/{project_id}/automations", status_code=status.HTTP_201_CREATED)
    async def create_automation(project_id: int, req: AutomationCreateRequest) -> dict[str, Any]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.automations is not None
                return _dump(
                    await uow.automations.create(
                        domain.Automation(
                            project_id=project_id,
                            name=req.name,
                            trigger_kind=req.trigger_kind,
                            interval_seconds=req.interval_seconds,
                            goal_template=req.goal_template,
                            profile_id=req.profile_id,
                            profile_snapshot=req.profile_snapshot,
                            budgets=req.budgets,
                            session_id=req.session_id,
                            metadata=req.metadata,
                        )
                    )
                )
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.get("/projects/{project_id}/automations")
    async def list_automations(project_id: int) -> list[dict[str, Any]]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.automations is not None
                return [_dump(item) for item in await uow.automations.list(project_id)]
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.post("/automations/{automation_id}/run")
    async def trigger_automation(automation_id: str, req: AutomationTriggerRequest) -> dict[str, Any]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.automations is not None
                return _dump(await uow.automations.trigger(automation_id, req.idempotency_key))
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.get("/automations/{automation_id}/runs")
    async def automation_runs(automation_id: str) -> list[dict[str, Any]]:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.automations is not None
                return [_dump(item) for item in await uow.automations.list_runs(automation_id)]
        except Exception as exc:
            _http(exc)
            raise AssertionError("unreachable") from exc

    @router.post("/automations/{automation_id}/pause")
    async def pause_automation(automation_id: str) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.automations is not None
            return _dump(await uow.automations.set_status(automation_id, AutomationStatus.PAUSED))

    @router.post("/automations/{automation_id}/resume")
    async def resume_automation(automation_id: str) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.automations is not None
            return _dump(await uow.automations.set_status(automation_id, AutomationStatus.ACTIVE))

    @router.post("/automations/{automation_id}/disable")
    async def disable_automation(automation_id: str) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.automations is not None
            return _dump(await uow.automations.set_status(automation_id, AutomationStatus.DISABLED))

    return router
