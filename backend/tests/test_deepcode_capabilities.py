from __future__ import annotations

import pytest
from localforge.models import domain
from localforge.models.enums import AutomationRunStatus
from localforge.services.deepcode_capabilities import ModelCatalogService
from localforge.services.tenant_context import TenantContext, bind_context, reset_context
from localforge.skills.registry import SkillDefinition, SkillRegistry
from localforge.storage import UnitOfWork


class FakeOmniRoute:
    async def get_models(self):
        return [{"id": "fake/model", "capabilities": {"vision": True}}]

    async def verify_json_contract(self, model_name: str):
        return model_name == "fake/model"


async def _project(db_manager, tmp_path, tenant="tenant-a"):
    token = bind_context(TenantContext(tenant_id=tenant, user_id="tester"))
    try:
        async with UnitOfWork(db_manager) as uow:
            project = await uow.projects.create_project(domain.Project(name="Capability project", root_path=str(tmp_path / tenant), default_branch="main"))
            await uow.commit()
            return project
    finally:
        reset_context(token)


@pytest.mark.asyncio
async def test_model_catalog_skill_binding_and_automation_are_durable(db_manager, tmp_path):
    project = await _project(db_manager, tmp_path)
    token = bind_context(TenantContext(tenant_id="tenant-a", user_id="alice"))
    try:
        async with UnitOfWork(db_manager) as uow:
            catalog = ModelCatalogService(uow.session, client_factory=FakeOmniRoute)
            entries = await catalog.discover(project.id)
            assert [item.model_name for item in entries] == ["fake/model"]
            verification = await catalog.probe(project.id, "fake/model")
            assert verification.status.value == "VERIFIED"
            assert "api_key" not in str(verification.model_dump()).lower()

            session = await uow.engineering.create_session(project_id=project.id)
            await uow.engineering.create_goal(session_id=session.id, objective="bind skill")
            turn = await uow.engineering.admit_turn(session_id=session.id, input_text="run", idempotency_key="cap-1")
            skill = SkillDefinition(name="stable", purpose="test", manifest_version=2)
            binding = await uow.skill_bindings.bind(project_id=project.id, session_id=session.id, turn_id=turn.id, skill=skill)
            assert binding.digest == SkillRegistry.manifest_digest(skill)
            assert binding.version == 2

            automation = await uow.automations.create(domain.Automation(project_id=project.id, name="manual-check", goal_template={"objective": "check"}))
            first = await uow.automations.trigger(automation.id, "auto-1")
            second = await uow.automations.trigger(automation.id, "auto-1")
            assert first.status == AutomationRunStatus.COMPLETED
            assert second.id == first.id
            assert first.evidence["turn_id"]
    finally:
        reset_context(token)


@pytest.mark.asyncio
async def test_capabilities_are_tenant_isolated(db_manager, tmp_path):
    project = await _project(db_manager, tmp_path, "tenant-a")
    token = bind_context(TenantContext(tenant_id="tenant-b", user_id="bob"))
    try:
        async with UnitOfWork(db_manager) as uow:
            with pytest.raises(ValueError):
                await uow.model_catalog.list_entries(project.id)
            with pytest.raises(ValueError):
                await uow.automations.list(project.id)
    finally:
        reset_context(token)
