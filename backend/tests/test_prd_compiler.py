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


def test_deterministic_extractor_groups_numbered_prd_sections():
    markdown = """# Product

## Requisitos Funcionais

1. **Gestão de Itens de Trabalho**:
   - Criar, editar, listar e deletar itens.
   - Cada item possui: `id`, `title`, `status`.

2. **Máquina de Estados Determinística**:
   - Transições válidas de status:
     - `backlog` -> `in_progress`
   - Transições proibidas:
     - `done` não pode retornar a `backlog`.
"""
    plan = DeterministicPRDExtractor().extract(markdown)

    assert [task.title for task in plan.tasks] == [
        "Gestão de Itens de Trabalho",
        "Máquina de Estados Determinística",
    ]
    assert all(not task.title.endswith(":") for task in plan.tasks)
    assert any("Criar, editar" in item for item in plan.tasks[0].acceptance_criteria)
    assert any("done" in item for item in plan.tasks[1].acceptance_criteria)


def test_deterministic_extractor_does_not_turn_acceptance_bullets_into_tasks():
    markdown = """# Product

## Functional Requirements

1. **Work Item Management**:
   - Create and edit work items.

2. **State Machine**:
   - Legal status transitions are enforced.

## Criterios de Aceitacao
- Empty titles are rejected.
- Illegal transitions are blocked.
- JSON export includes active items.
"""
    plan = DeterministicPRDExtractor().extract(markdown)

    assert [task.title for task in plan.tasks] == [
        "Work Item Management",
        "State Machine",
    ]
    assert all("Empty titles" not in item for item in plan.tasks[0].acceptance_criteria)
    assert any("Empty titles" in item for item in plan.tasks[1].acceptance_criteria)
    assert any("Illegal transitions" in item for item in plan.tasks[1].acceptance_criteria)


def test_deterministic_extractor_treats_short_acceptance_heading_as_project_gate():
    markdown = """# Product

## Requirements

1. **Create items**
   - Items can be created and listed.

## Aceitacao
- Human review remains required.
"""
    plan = DeterministicPRDExtractor().extract(markdown)

    assert [task.title for task in plan.tasks] == ["Create items"]
    assert any("Human review remains required" in item for item in plan.tasks[0].acceptance_criteria)


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
    assert imported.tasks_created == 2  # 1 feature task + 1 integration task

    async with UnitOfWork(db_manager) as uow:
        assert uow.tasks is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)
    assert tasks[0].title == "Load Markdown"
    assert "Integration" in tasks[1].title
    assert tasks[1].dependency_task_ids == [tasks[0].id]



@pytest.mark.anyio
async def test_import_prd_creates_architecture_contract_and_task_packets(db_manager, tmp_path):
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text(
        "# PRD\n\n## Calculator\n- Implement numeric entry\n- Implement TVM solving\n",
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
    assert (
        tasks[0]
        .metadata["task_contract"]["canonical_test_command"]
        .startswith("python -m pytest tests/")
    )


def test_architecture_contract_uses_explicit_domain_neutral_task_packets():
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    api_title = "Add audit event API"
    dashboard_title = "Build audit dashboard"
    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[
                ExtractedTask(
                    title=api_title,
                    description="",
                    expected_files=[
                        "backend/localforge/api/audit.py",
                        "backend/tests/test_audit_api.py",
                    ],
                    metadata={
                        "required_public_apis": ["list_audit_events"],
                        "forbidden_dependencies": ["unsafe-shell"],
                    },
                ),
                ExtractedTask(
                    title=dashboard_title,
                    description="",
                    expected_files=[
                        "frontend/src/components/audit_dashboard.tsx",
                        "frontend/src/components/audit_dashboard.test.tsx",
                    ],
                    metadata={"depends_on": [api_title]},
                ),
                ExtractedTask(title="Document audit workflow", description=""),
            ]
        )
    )

    assert contract.task_contracts[api_title].required_public_apis == ["list_audit_events"]
    assert contract.task_contracts[api_title].allowed_files == [
        "backend/localforge/api/audit.py",
        "backend/tests/test_audit_api.py",
    ]
    assert contract.task_contracts[api_title].forbidden_dependencies == ["unsafe-shell"]
    assert contract.dependency_graph[dashboard_title] == [api_title]
    assert contract.task_contracts[dashboard_title].seniority_class == "chief_led"
    assert (
        contract.task_contracts["Document audit workflow"].canonical_test_command
        == "git diff --check"
    )


def test_keyboard_mapping_is_not_misclassified_as_visual_work() -> None:
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    title = "Map physical keyboard keys to calculator buttons"
    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[
                ExtractedTask(
                    title=title,
                    description="Wire keyboard events to existing controls.",
                    expected_files=["app/index.html", "tests/test_keyboard.py"],
                )
            ]
        )
    ).task_contracts[title]

    assert contract.visual_required is False
    assert contract.seniority_class == "local_assisted"


def test_web_prd_without_paths_uses_shared_product_surface():
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[
                ExtractedTask(title="Design calculator keypad", description=""),
                ExtractedTask(title="Implement RPN stack registers", description=""),
            ]
        )
    )

    assert contract.task_contracts["Implement RPN stack registers"].allowed_files == [
        "app/index.html",
        "tests/test_implement_rpn_stack_registers.py",
    ]
    assert contract.task_contracts["Design calculator keypad"].visual_required is True
    assert contract.task_contracts["Design calculator keypad"].seniority_class == "chief_led"
    assert contract.task_contracts["Implement RPN stack registers"].visual_required is False
    assert (
        contract.task_contracts["Implement RPN stack registers"].seniority_class
        == "local_assisted"
    )


def test_visual_web_tasks_receive_reference_contract_from_workspace(tmp_path):
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "hp12c_platinum_design_target.png").write_bytes(b"reference")
    title = "Design the calculator chassis and keypad layout"

    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[ExtractedTask(title=title, description="", expected_files=["app/index.html"])]
        ),
        project_root=tmp_path,
    ).task_contracts[title]

    assert contract.visual_required is True
    assert contract.visual_reference_image == "docs/hp12c_platinum_design_target.png"
    assert contract.visual_actual_output == "app/index.html"
    assert contract.visual_viewport == "1280x720"


def test_visual_contract_honors_metadata_and_rejects_escape_paths():
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    title = "Implement the product surface"
    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[
                ExtractedTask(
                    title=title,
                    description="",
                    expected_files=["app/index.html"],
                    metadata={
                        "visual_required": True,
                        "visual_reference_image": "../outside.png",
                        "visual_actual_output": "C:/outside.html",
                    },
                )
            ]
        )
    ).task_contracts[title]

    assert contract.visual_required is True
    assert contract.visual_reference_image is None
    assert contract.visual_actual_output is None


@pytest.mark.anyio
async def test_import_prd_persists_explicit_contract_dependencies(db_manager, tmp_path):
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text("# Audit work\n", encoding="utf-8")
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "epics": [{"title": "Audit", "summary": "Audit work"}],
                    "tasks": [
                        {
                            "epic_title": "Audit",
                            "title": "Create audit API",
                            "description": "Expose audit events.",
                            "expected_files": [
                                "backend/localforge/api/audit.py",
                                "backend/tests/test_audit_api.py",
                            ],
                        },
                        {
                            "epic_title": "Audit",
                            "title": "Create audit dashboard",
                            "description": "Display audit events.",
                            "expected_files": [
                                "frontend/src/components/audit_dashboard.tsx",
                                "frontend/src/components/audit_dashboard.test.tsx",
                            ],
                            "metadata": {"depends_on": ["Create audit API"]},
                        },
                    ],
                }
            )
        ]
    )
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.create_project(
            domain.Project(name="Dependency", root_path=str(tmp_path), default_branch="main")
        )
        assert project.id is not None

    await import_prd(prd_path, project.id, db_manager=db_manager, llm_provider=provider)

    async with UnitOfWork(db_manager) as uow:
        assert uow.tasks is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)
    by_title = {task.title: task for task in tasks}

    assert by_title["Create audit dashboard"].dependency_task_ids == [
        by_title["Create audit API"].id
    ]


@pytest.mark.anyio
async def test_import_prd_appends_integration_task_depending_on_all_preceding_tasks(db_manager, tmp_path):
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text(
        "# App\n\n## Core\n- Task A\n- Task B\n- Task C\n",
        encoding="utf-8",
    )
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.create_project(
            domain.Project(name="IntegrationApp", root_path=str(tmp_path), default_branch="main")
        )
        assert project.id is not None

    await import_prd(prd_path, project.id, db_manager=db_manager, dry_run=False)

    async with UnitOfWork(db_manager) as uow:
        assert uow.tasks is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)

    by_title = {task.title: task for task in tasks}
    assert "Task A" in by_title
    assert "Task B" in by_title
    assert "Task C" in by_title
    integration_task = next(t for t in tasks if "Integration & Release Assembly" in t.title)
    assert integration_task.metadata.get("is_integration_task") is True

    feature_ids = {by_title["Task A"].id, by_title["Task B"].id, by_title["Task C"].id}
    assert set(integration_task.dependency_task_ids) == feature_ids

