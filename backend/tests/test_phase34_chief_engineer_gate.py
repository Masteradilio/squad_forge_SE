import asyncio
import json

import pytest
from localforge.chief_engineer.service import (
    ChiefEngineerRepairPlan,
    ChiefEngineerService,
    _estimate_message_tokens,
)
from localforge.llm.fake import FakeLLMProvider
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason, RunMode, RunStatus
from localforge.prd.contracts import build_architecture_contract
from localforge.prd.schemas import ExtractedPlan, ExtractedTask
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager
from pydantic import ValidationError


def test_chief_engineer_contract_review_records_paid_call(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase34.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "approved": True,
                    "summary": "Contract is coherent and bounded.",
                    "required_changes": [],
                    "risk_notes": ["Keep public APIs frozen."],
                }
            )
        ]
    )
    contract = build_architecture_contract(
        ExtractedPlan(
            tasks=[
                ExtractedTask(
                    title="Implement TVM solving",
                    description="Implement TVM",
                    risk_level="high",
                )
            ]
        )
    )

    async def exercise() -> dict[str, object]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            assert uow.model_calls is not None
            project = await uow.projects.create_project(
                domain.Project(name="Phase 34", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.UNATTENDED,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                    resource_limits={"max_paid_calls": 2},
                )
            )
            assert run.id is not None
            review = await ChiefEngineerService(uow).review_contract(
                project_id=project.id,
                run_id=run.id,
                contract=contract,
                provider=provider,
                model="minimax/minimax-m3",
            )
            calls = await uow.model_calls.list_calls(project_id=project.id, run_id=run.id)
            return {
                "approved": review.approved,
                "reason": calls[0].reason,
                "input_tokens": calls[0].input_tokens,
                "output_tokens": calls[0].output_tokens,
            }

    data = asyncio.run(exercise())
    asyncio.run(manager.close())

    assert data["approved"] is True
    assert data["reason"] == ChiefEngineerCallReason.CONTRACT_FREEZE
    assert int(data["input_tokens"]) > 0
    assert int(data["output_tokens"]) > 0


def test_chief_engineer_repair_plan_rejects_empty_actions():
    with pytest.raises(ValidationError):
        ChiefEngineerRepairPlan.model_validate(
            {
                "summary": "No-op",
                "failure_class": "SEMANTIC_TEST_FAILURE",
                "actions": [],
                "risk_notes": [],
            }
        )


def test_multimodal_budget_estimate_does_not_count_base64_as_text():
    image_data_url = "data:image/jpeg;base64," + ("A" * 500_000)
    estimate = _estimate_message_tokens(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "repair the visual layout"},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ]
    )

    assert estimate < 10_000


def test_chief_engineer_semantic_repair_records_paid_call(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase34_repair.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "summary": "Fix missing export.",
                    "failure_class": "MISSING_IMPORT",
                    "actions": [
                        {
                            "operation": "update_file",
                            "file": "calculator/core.py",
                            "code": "class Calculator: pass\n",
                        }
                    ],
                    "risk_notes": [],
                }
            )
        ]
    )

    async def exercise() -> dict[str, object]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            assert uow.model_calls is not None
            project = await uow.projects.create_project(
                domain.Project(
                    name="Phase 34 Repair", root_path=str(tmp_path), default_branch="main"
                )
            )
            assert project.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.UNATTENDED,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                    resource_limits={"max_paid_calls": 2},
                )
            )
            assert run.id is not None
            plan = await ChiefEngineerService(uow).plan_semantic_repair(
                project_id=project.id,
                run_id=run.id,
                task_id=123,
                task_contract={"allowed_files": ["calculator/core.py"]},
                changed_files_context="--- calculator/core.py ---\n",
                validation_output="ImportError: cannot import name Calculator",
                provider=provider,
                model="minimax/minimax-m3",
            )
            calls = await uow.model_calls.list_calls(project_id=project.id, run_id=run.id)
            return {
                "path": plan.runtime_actions()[0].path,
                "reason": calls[0].reason,
                "task_id": calls[0].task_id,
            }

    data = asyncio.run(exercise())
    asyncio.run(manager.close())

    assert data["path"] == "calculator/core.py"
    assert data["reason"] == ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN
    assert data["task_id"] == 123
