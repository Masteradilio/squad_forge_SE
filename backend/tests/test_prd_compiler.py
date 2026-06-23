import json

import pytest
from localforge.llm.fake import FakeLLMProvider
from localforge.models import domain
from localforge.models.enums import DocumentKind
from localforge.prd.compiler import import_prd
from localforge.prd.extractor import DeterministicPRDExtractor
from localforge.prd.loader import MarkdownDocumentLoader, sha256_text
from localforge.prd.model_assisted import generate_model_assisted_plan
from localforge.prd.sizing import size_task
from localforge.services.project import ProjectService
from localforge.storage import UnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_markdown_loader_hashes_and_detects_changes(
    db_manager, db_session: AsyncSession, tmp_path
):
    service = ProjectService(db_session)
    project = await service.create_project(
        domain.Project(name="PRD", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text("# Product\n\n- Build importer\n", encoding="utf-8")

    loader = MarkdownDocumentLoader(service)
    first = await loader.load(project.id, prd_path, DocumentKind.PRD)
    second = await loader.load(project.id, prd_path, DocumentKind.PRD)
    prd_path.write_text("# Product\n\n- Build importer\n- Add dry run\n", encoding="utf-8")
    third = await loader.load(project.id, prd_path, DocumentKind.PRD)

    assert first.changed is True
    assert second.changed is False
    assert third.changed is True
    assert first.content_hash == sha256_text("# Product\n\n- Build importer\n")


def test_deterministic_extractor_reads_headings_bullets_checkboxes_and_tables():
    markdown = """# App

## Authentication
- Add login
- [ ] Add logout

| Feature | Acceptance |
| --- | --- |
| Session timeout | User is logged out |
"""
    plan = DeterministicPRDExtractor().extract(markdown)

    assert [epic.title for epic in plan.epics] == ["Authentication"]
    titles = [task.title for task in plan.tasks]
    assert "Add login" in titles
    assert "Add logout" in titles
    assert "Session timeout" in titles
    assert all(task.acceptance_criteria for task in plan.tasks)


@pytest.mark.anyio
async def test_model_assisted_generation_uses_fake_llm_and_validates_json():
    payload = {
        "epics": [{"title": "Importer", "summary": "Import PRDs", "acceptance_summary": "Tasks"}],
        "tasks": [
            {
                "epic_title": "Importer",
                "title": "Load markdown",
                "description": "Read Markdown files",
                "acceptance_criteria": ["Reads UTF-8 Markdown"],
                "risk_level": "low",
            }
        ],
    }
    provider = FakeLLMProvider(responses=[json.dumps(payload)])

    plan = await generate_model_assisted_plan(provider, "# PRD")

    assert plan.tasks[0].title == "Load markdown"
    assert provider.last_payload["response_schema"] is not None


@pytest.mark.anyio
async def test_invalid_model_json_fails_without_mutating_state(db_manager, tmp_path):
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text("# PRD\n\n## Importer\n- Load Markdown\n", encoding="utf-8")
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.create_project(
            domain.Project(name="InvalidLLM", root_path=str(tmp_path), default_branch="main")
        )
        assert project.id is not None

    provider = FakeLLMProvider(responses=["not json", "{still not json"])
    with pytest.raises(ValueError):
        await import_prd(
            prd_path,
            project_id=project.id,
            db_manager=db_manager,
            dry_run=False,
            llm_provider=provider,
        )

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert await uow.projects.list_documents_for_project(project.id) == []
        assert await uow.tasks.list_tasks_for_project(project.id) == []


def test_task_sizing_flags_large_ambiguous_multi_component_work():
    result = size_task(
        title="Build auth and billing and dashboard",
        description="Modify api.py, auth.py, billing.py, dashboard.tsx, tests.py",
        acceptance_criteria=["Works"],
        risk_level="high",
    )

    assert result.needs_split is True
    assert "high risk" in result.reasons
    assert "ambiguous acceptance" in result.reasons


@pytest.mark.anyio
async def test_import_prd_dry_run_does_not_persist_and_normal_import_creates_tasks(
    db_manager, tmp_path
):
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text("# PRD\n\n## Importer\n- Load Markdown\n", encoding="utf-8")
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.create_project(
            domain.Project(name="Import", root_path=str(tmp_path), default_branch="main")
        )
        assert project.id is not None

    dry = await import_prd(prd_path, project.id, db_manager=db_manager, dry_run=True)
    assert dry.persisted is False

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert await uow.projects.list_documents_for_project(project.id) == []

    imported = await import_prd(prd_path, project.id, db_manager=db_manager, dry_run=False)
    assert imported.persisted is True
    assert imported.tasks_created == 1

    async with UnitOfWork(db_manager) as uow:
        assert uow.tasks is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)
    assert tasks[0].title == "Load Markdown"


@pytest.mark.anyio
async def test_import_prd_creates_architecture_contract_and_task_packets(
    db_manager, tmp_path
):
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text(
        "# PRD\n\n"
        "## Calculator\n"
        "- Implement numeric entry\n"
        "- Implement TVM solving\n",
        encoding="utf-8",
    )
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.create_project(
            domain.Project(name="Contract", root_path=str(tmp_path), default_branch="main")
        )
        assert project.id is not None

    imported = await import_prd(prd_path, project.id, db_manager=db_manager, dry_run=False)

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        documents = await uow.projects.list_documents_for_project(project.id)
        tasks = await uow.tasks.list_tasks_for_project(project.id)

    architecture_docs = [doc for doc in documents if doc.kind == DocumentKind.ARCHITECTURE]
    assert imported.architecture_contract_path
    assert len(architecture_docs) == 1
    assert (tmp_path / imported.architecture_contract_path).exists()
    assert tasks[0].metadata["contract_id"] == "architecture-contract-v1"
    assert tasks[0].metadata["task_contract"]["allowed_files"]
    assert tasks[0].metadata["task_contract"]["canonical_test_command"].startswith(
        "python -m pytest tests/"
    )


def test_architecture_contract_uses_bounded_calculator_task_packets():
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[
                ExtractedTask(title="Initialize calculator app structure", description=""),
                ExtractedTask(title="Implement four-level RPN stack", description=""),
                ExtractedTask(title="Implement TVM register model", description=""),
                ExtractedTask(title="Implement TVM solving", description=""),
                ExtractedTask(title="Implement NPV and IRR", description=""),
                ExtractedTask(title="Prepare PR-ready summary", description=""),
            ]
        )
    )

    assert contract.task_contracts["Initialize calculator app structure"].required_public_apis == [
        "Calculator",
        "CalculatorState",
    ]
    assert contract.task_contracts["Implement four-level RPN stack"].allowed_files == [
        "calculator/stack.py",
        "tests/test_rpn_stack.py",
    ]
    assert contract.task_contracts["Implement TVM register model"].allowed_files != (
        contract.task_contracts["Implement TVM solving"].allowed_files
    )
    assert "Implement TVM register model" in contract.dependency_graph["Implement TVM solving"]
    assert contract.task_contracts["Implement NPV and IRR"].risk_level == "high"
    assert "docs/pr_ready_summary.md" in (
        contract.task_contracts["Prepare PR-ready summary"].canonical_test_command
    )
