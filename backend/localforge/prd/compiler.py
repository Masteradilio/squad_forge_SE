from pathlib import Path

from pydantic import BaseModel, Field

from localforge.llm.base import BaseLLMProvider
from localforge.models import domain
from localforge.models.enums import DocumentKind, TaskStatus
from localforge.prd.contracts import build_architecture_contract
from localforge.prd.extractor import DeterministicPRDExtractor
from localforge.prd.loader import MarkdownDocumentLoader
from localforge.prd.model_assisted import generate_model_assisted_plan
from localforge.prd.schemas import ExtractedPlan
from localforge.prd.sizing import size_task
from localforge.storage.database import DatabaseManager
from localforge.storage.transactions import UnitOfWork


class ImportPRDResult(BaseModel):
    persisted: bool
    document_hash: str
    changed: bool
    epics_created: int
    tasks_created: int
    epics: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    architecture_contract_path: str | None = None


async def import_prd(
    path: str | Path,
    project_id: int,
    *,
    db_manager: DatabaseManager,
    dry_run: bool = False,
    llm_provider: BaseLLMProvider | None = None,
) -> ImportPRDResult:
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        loader = MarkdownDocumentLoader(uow.projects)
        loaded = await loader.load(project_id, path, DocumentKind.PRD, persist=False)
        deterministic = DeterministicPRDExtractor().extract(loaded.content)
        plan = (
            await generate_model_assisted_plan(llm_provider, loaded.content)
            if llm_provider is not None
            else deterministic
        )

        if dry_run:
            return _result(False, loaded.content_hash, loaded.changed, plan)

        assert uow.tasks is not None
        persisted_doc = await loader.load(
            project_id,
            path,
            DocumentKind.PRD,
            persist=True,
            parsed_summary=_summary(plan),
        )
        project = await uow.projects.get_project(project_id)
        if project is None:
            raise ValueError("Project not found for PRD import.")
        contract = build_architecture_contract(plan)
        contract_rel_path = ".localforge/contracts/architecture_contract.json"
        contract_path = Path(project.root_path) / contract_rel_path
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            contract.model_dump_json(indent=2),
            encoding="utf-8",
        )
        await loader.load(
            project_id,
            contract_path,
            DocumentKind.ARCHITECTURE,
            persist=True,
            parsed_summary=(
                f"{len(contract.module_map)} modules, "
                f"{len(contract.task_contracts)} task contracts"
            ),
        )
        epic_by_title: dict[str, domain.Epic] = {}
        for index, epic in enumerate(plan.epics, start=1):
            created = await uow.tasks.create_epic(
                domain.Epic(
                    project_id=project_id,
                    title=epic.title,
                    summary=epic.summary,
                    source_document_id=persisted_doc.document.id,
                    priority=epic.priority or index,
                    acceptance_summary=epic.acceptance_summary,
                )
            )
            epic_by_title[created.title] = created

        existing_tasks = await uow.tasks.list_tasks_for_project(project_id)
        next_number = len(existing_tasks) + 1
        for task in plan.tasks:
            sizing = size_task(
                title=task.title,
                description=task.description,
                acceptance_criteria=task.acceptance_criteria,
                risk_level=task.risk_level,
                expected_files=task.expected_files,
            )
            persisted_epic = epic_by_title.get(task.epic_title or "")
            created_key = f"LF-PRD-{next_number:03d}"
            next_number += 1
            task_contract = contract.task_contracts.get(task.title)
            await uow.tasks.create_task(
                domain.Task(
                    project_id=project_id,
                    epic_id=persisted_epic.id if persisted_epic else None,
                    key=created_key,
                    title=task.title,
                    description=task.description,
                    acceptance_criteria=sizing.acceptance_criteria,
                    risk_level=sizing.risk_level,
                    status=TaskStatus.BACKLOG,
                    metadata={
                        **task.metadata,
                        "source": "prd_compiler",
                        "contract_id": contract.contract_id,
                        "architecture_contract_path": contract_rel_path,
                        "task_contract": (
                            task_contract.model_dump(mode="json")
                            if task_contract
                            else {}
                        ),
                        "sizing": sizing.model_dump(),
                        "source_document_id": persisted_doc.document.id,
                    },
                )
            )

        return _result(
            True,
            loaded.content_hash,
            loaded.changed,
            plan,
            architecture_contract_path=contract_rel_path,
        )


def _result(
    persisted: bool,
    document_hash: str,
    changed: bool,
    plan: ExtractedPlan,
    architecture_contract_path: str | None = None,
) -> ImportPRDResult:
    return ImportPRDResult(
        persisted=persisted,
        document_hash=document_hash,
        changed=changed,
        epics_created=len(plan.epics),
        tasks_created=len(plan.tasks),
        epics=[epic.title for epic in plan.epics],
        tasks=[task.title for task in plan.tasks],
        architecture_contract_path=architecture_contract_path,
    )


def _summary(plan: ExtractedPlan) -> str:
    return f"{len(plan.epics)} epics, {len(plan.tasks)} tasks"
