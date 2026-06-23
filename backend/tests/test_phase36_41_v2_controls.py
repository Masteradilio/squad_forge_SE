import asyncio
import json
from pathlib import Path

from localforge.chief_engineer.final_review import FinalReviewService
from localforge.chief_engineer.service import ChiefEngineerService
from localforge.contracts.change_requests import (
    ContractChangeRequest,
    ContractChangeService,
)
from localforge.contracts.verifier import ContractVerifier
from localforge.integration.validator import IntegrationBranchValidator
from localforge.llm.fake import FakeLLMProvider
from localforge.models import domain
from localforge.models.enums import (
    ChiefEngineerCallReason,
    FailureClass,
    RunMode,
    RunStatus,
)
from localforge.repair.classifier import FailureClassifier
from localforge.routing.capabilities import LocalWorkerCapabilityRouter
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_capability_router_escalates_high_risk_and_logs_rationale():
    router = LocalWorkerCapabilityRouter()
    task = domain.Task(
        project_id=1,
        key="LF-3601",
        title="Change public architecture",
        description="Cross-module API redesign",
        risk_level="high",
        metadata={"task_contract": {"allowed_files": ["a.py", "b.py", "c.py"]}},
    )

    decision = router.route(task, previous_failure_class=FailureClass.SEMANTIC_TEST_FAILURE)

    assert decision.model_tier == "chief_engineer"
    assert decision.escalate is True
    assert "high risk" in decision.rationale.lower()
    assert "semantic" in decision.rationale.lower()


def test_contract_verifier_reports_scope_import_api_and_dependency_failures(tmp_path):
    (tmp_path / "allowed.py").write_text("import scipy\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("print('drift')\n", encoding="utf-8")
    contract = {
        "allowed_files": ["allowed.py"],
        "required_public_apis": ["Calculator"],
        "forbidden_dependencies": ["scipy"],
        "canonical_test_command": "python -m pytest -q",
    }

    result = ContractVerifier().verify(
        worktree_path=str(tmp_path),
        task_contract=contract,
        changed_files=["allowed.py", "outside.py"],
    )

    failure_classes = {finding.failure_class for finding in result.findings}
    assert result.passed is False
    assert FailureClass.CONTRACT_DRIFT in failure_classes
    assert FailureClass.FORBIDDEN_DEPENDENCY in failure_classes
    assert FailureClass.PUBLIC_API_MISMATCH in failure_classes


def test_failure_classifier_prefers_deterministic_playbooks():
    classified = FailureClassifier().classify(
        output="ModuleNotFoundError: No module named 'calculator'",
        task_contract={"allowed_files": ["calculator.py"]},
        attempt_count=1,
    )

    assert classified.failure_class == FailureClass.MISSING_IMPORT
    assert classified.escalate_to_chief is False
    assert "approved module map" in classified.playbook.lower()


def test_contract_change_service_requires_chief_approval_for_new_dependency(tmp_path):
    contract = {
        "allowed_files": ["core.py"],
        "forbidden_dependencies": ["scipy"],
        "required_public_apis": [],
    }
    request = ContractChangeRequest(
        task_key="LF-3901",
        requested_files=["core.py"],
        requested_dependencies=["scipy"],
        requested_public_apis=[],
        rationale="Need solver dependency",
    )

    decision = ContractChangeService().evaluate(contract, request)

    assert decision.requires_chief_engineer is True
    assert decision.approved is False
    assert "dependency" in decision.reason.lower()


def test_integration_validator_classifies_command_failure(tmp_path):
    (tmp_path / "fail.py").write_text("raise SystemExit(3)\n", encoding="utf-8")

    result = IntegrationBranchValidator().validate(
        worktree_path=str(tmp_path),
        task_keys=["LF-4001"],
        test_command=f"python {Path('fail.py')}",
    )

    assert result.passed is False
    assert result.failure_class == FailureClass.SEMANTIC_TEST_FAILURE
    assert result.task_keys == ["LF-4001"]


def test_final_review_records_chief_engineer_paid_call(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase41.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "approved": True,
                    "summary": "Diff respects contract and evidence is sufficient.",
                    "required_changes": [],
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
                domain.Project(name="Phase 41", root_path=str(tmp_path), default_branch="main")
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
            review = await FinalReviewService(
                ChiefEngineerService(uow)
            ).review_pr(
                project_id=project.id,
                run_id=run.id,
                task_id=41,
                provider=provider,
                model="minimax/minimax-m3",
                task_contract={"allowed_files": ["core.py"]},
                diff_summary="M core.py",
                verifier_results={"passed": True, "findings": []},
                test_output_summary="1 passed",
                risk_notes=[],
            )
            calls = await uow.model_calls.list_calls(project_id=project.id, run_id=run.id)
            return {"approved": review.approved, "reason": calls[0].reason}

    data = asyncio.run(exercise())
    asyncio.run(manager.close())

    assert data["approved"] is True
    assert data["reason"] == ChiefEngineerCallReason.FINAL_PR_REVIEW
