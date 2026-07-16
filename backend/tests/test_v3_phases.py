import pytest
from unittest.mock import MagicMock
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason, FailureClass
from localforge.chief_engineer.bundler import EconomyPromptBundler
from localforge.routing.delegation import LocalWorkDelegationContract
from localforge.storage import UnitOfWork

def test_economy_prompt_bundler_redacts_keys():
    bundler = EconomyPromptBundler()
    text_with_key = "My API key is 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 and it is secret."
    redacted = bundler.redact_sensitive_info(text_with_key)
    assert "sk-or-v" not in redacted
    assert "[REDACTED_API_KEY]" in redacted

    text_with_pass = "password='my-super-secret-password' and token = \"abc\""
    redacted_pass = bundler.redact_sensitive_info(text_with_pass)
    assert "my-super-secret-password" not in redacted_pass
    assert "[REDACTED_PASSWORD]" in redacted_pass
    assert "[REDACTED_TOKEN]" in redacted_pass

def test_economy_prompt_bundler_compresses_errors():
    bundler = EconomyPromptBundler()
    huge_error = "Traceback:\n" + "same error line\n" * 100
    compressed = bundler.compress_diff_and_errors(huge_error, max_chars=200)
    assert "[repeated" in compressed

def test_economy_prompt_bundler_snippet_selection():
    bundler = EconomyPromptBundler(max_file_chars=50)
    file_content = "\n".join([f"line_{i}" for i in range(1, 100)])
    error_output = 'File "app.py", line 50'
    snippet = bundler.select_relevant_snippets("app.py", file_content, error_output)
    
    assert "Line 50: line_50" in snippet

def test_local_work_delegation_limits():
    delegation = LocalWorkDelegationContract(max_file_size=100)
    task = domain.Task(
        project_id=1,
        key="LF-100",
        title="Simple task",
        description="Just edit a simple file",
        risk_level="low",
    )
    task_run = domain.TaskRun(id=1, run_id=1, task_id=100, worktree_path=None)
    
    is_allowed, rationale = delegation.evaluate_delegation(task, task_run)
    assert is_allowed is True

    # High risk escalates
    high_risk_task = domain.Task(
        project_id=1,
        key="LF-100",
        title="High risk task",
        description="Just edit a simple file",
        risk_level="high",
    )
    is_allowed, rationale = delegation.evaluate_delegation(high_risk_task, task_run)
    assert is_allowed is False
    assert "requires Chief Engineer" in rationale

    chief_contract_task = domain.Task(
        project_id=1,
        key="LF-101",
        title="Contracted Chief task",
        description="Looks simple, but routing contract is authoritative.",
        metadata={"task_contract": {"seniority_class": "chief_only"}},
    )
    is_allowed, rationale = delegation.evaluate_delegation(chief_contract_task, task_run)
    assert is_allowed is False
    assert "Chief Engineer" in rationale

    chief_led_task = domain.Task(
        project_id=1,
        key="LF-102",
        title="Chief-led task",
        description="Chief Engineer should guide, but bounded local draft is allowed.",
        metadata={"task_contract": {"seniority_class": "chief_led"}},
        risk_level="medium",
    )
    is_allowed, rationale = delegation.evaluate_delegation(chief_led_task, task_run)
    assert is_allowed is True


@pytest.mark.asyncio
async def test_api_simulation_service(db_session):
    from localforge.services.simulation import APISimulationService
    from localforge.services.model_calls import ModelCallLedgerService
    
    ledger_svc = ModelCallLedgerService(db_session)
    simulation_svc = APISimulationService(db_session)
    
    # 1. Record a large model call
    await ledger_svc.record_call(domain.ModelCallLedger(
        project_id=1,
        run_id=20,
        task_id=200,
        provider="openrouter",
        model="minimax/minimax-m3",
        reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
        input_tokens=100000,
        output_tokens=10000,
        estimated_cost_usd=0.042,
        status="success"
    ))
    
    # 2. Record a local model call (free)
    await ledger_svc.record_call(domain.ModelCallLedger(
        project_id=1,
        run_id=20,
        task_id=200,
        provider="ollama",
        model="granite4.1:8b",
        reason=ChiefEngineerCallReason.E2E_RETROSPECTIVE,
        input_tokens=50000,
        output_tokens=5000,
        estimated_cost_usd=0.0,
        status="success"
    ))
    
    # 3. Simulate costs
    sim = await simulation_svc.simulate_api_only_costs(project_id=1, run_id=20)
    
    assert sim["actual_paid_usd"] == 0.042
    assert sim["openai_simulated_usd"] > 0.0
    assert sim["google_simulated_usd"] > 0.0
    assert sim["anthropic_simulated_usd"] > 0.0
    assert sim["total_calls"] == 2


@pytest.mark.asyncio
async def test_v3_benchmark_harness(db_session):
    from localforge.benchmark.benchmark_runner import V3BenchmarkHarness
    from localforge.services.project import ProjectService
    from localforge.services.task import TaskService
    from localforge.services.cost_benchmark import CostBenchmarkService
    from localforge.services.simulation import APISimulationService
    
    # 1. Create a dummy project in DB
    proj_svc = ProjectService(db_session)
    project = await proj_svc.create_project(domain.Project(
        name="Benchmark Dummy",
        root_path="/tmp/benchmark_dummy",
        default_branch="main"
    ))
    
    async with UnitOfWork() as uow:
        uow.session = db_session
        uow.projects = proj_svc
        uow.tasks = TaskService(db_session)
        uow.cost_benchmark = CostBenchmarkService(db_session)
        uow.simulation = APISimulationService(db_session)
        
        harness = V3BenchmarkHarness(uow)
        report = await harness.run_benchmark(project.id)
        
    assert "error" not in report
    assert report["project_name"] == "Benchmark Dummy"
    
    md = harness.generate_markdown_summary(report)
    assert "# V3 Benchmark Acceptance Report" in md


def test_task_seniority_classification_evidence():
    from localforge.routing.capabilities import TaskSeniorityClassifier
    from localforge.models.enums import TaskSeniorityClass, FailureClass

    classifier = TaskSeniorityClassifier()

    # 1. Test case: file count > 5
    task_many_files = domain.Task(
        project_id=1,
        key="LF-101",
        title="Complex refactor",
        description="Edit multiple modules",
        metadata={
            "task_contract": {
                "allowed_files": ["f1.py", "f2.py", "f3.py", "f4.py", "f5.py", "f6.py"]
            }
        }
    )
    res = classifier.classify(task_many_files)
    assert res == TaskSeniorityClass.CHIEF_ONLY

    # 2. Test case: repeat failures
    task_normal = domain.Task(
        project_id=1,
        key="LF-102",
        title="Simple task",
        description="Just simple edit",
        metadata={
            "task_contract": {
                "allowed_files": ["f1.py"]
            }
        }
    )
    assert classifier.classify(task_normal) == TaskSeniorityClass.LOCAL_ASSISTED
    assert classifier.classify(task_normal, previous_failures=[FailureClass.SYNTAX_ERROR, FailureClass.EMPTY_DIFF]) == TaskSeniorityClass.CHIEF_ONLY


def test_task_contract_seniority_override_is_hard_rule():
    from localforge.routing.capabilities import TaskSeniorityClassifier
    from localforge.models.enums import TaskSeniorityClass

    classifier = TaskSeniorityClassifier()
    task = domain.Task(
        project_id=1,
        key="LF-103",
        title="Tiny looking task",
        description="One file only, but contract says Chief.",
        metadata={
            "task_contract": {
                "allowed_files": ["one.py"],
                "seniority_class": "chief_only",
            }
        },
    )

    assert classifier.classify(task) == TaskSeniorityClass.CHIEF_ONLY


def test_prd_contracts_classify_generic_visual_and_documentation_tasks():
    from localforge.prd.contracts import build_architecture_contract
    from localforge.prd.schemas import ExtractedPlan, ExtractedTask

    plan = ExtractedPlan(
        title="Operations Console",
        summary="small app",
        epics=[],
        tasks=[
            ExtractedTask(
                key="LF-1",
                title="Dashboard view",
                description="Render a four-column dashboard UI.",
                expected_files=[
                    "frontend/src/components/dashboard_view.tsx",
                    "frontend/src/components/dashboard_view.test.tsx",
                ],
            ),
            ExtractedTask(
                key="LF-2",
                title="Documentation summary",
                description="Write a short README summary.",
                expected_files=["docs/readme.md"],
            ),
        ],
    )

    contract = build_architecture_contract(plan)

    frontend = contract.task_contracts["Dashboard view"]
    docs = contract.task_contracts["Documentation summary"]
    assert frontend.seniority_class == "chief_led"
    assert frontend.visual_required is True
    assert docs.seniority_class == "local_only"


@pytest.mark.asyncio
async def test_local_model_call_is_recorded_in_ledger(db_session):
    from localforge.pipeline.engine import RolePipelineEngine
    from localforge.services.model_calls import ModelCallLedgerService

    engine = RolePipelineEngine(UnitOfWork(), project_id=1, run_id=20)
    engine.uow.model_calls = ModelCallLedgerService(db_session)
    task = domain.Task(project_id=1, key="LF-104", title="Local task", description="simple")

    await engine._record_local_model_call(
        task=task,
        model="granite4.1:8b",
        reason=ChiefEngineerCallReason.TASK_RISK_CLASSIFICATION,
        prompt="make a tiny change",
        response='{"actions":[]}',
    )

    calls = await engine.uow.model_calls.list_calls(project_id=1, run_id=20)
    assert len(calls) == 1
    assert calls[0].provider == "ollama"
    assert calls[0].estimated_cost_usd == 0.0
    assert calls[0].metadata["v3_economy_first"] is True


def test_v4_benchmark_requires_all_tasks_pr_ready_for_acceptance():
    from scripts.run_benchmark_v4_only import classify_benchmark_status

    status, blockers = classify_benchmark_status(
        preflight_failed=False,
        task_statuses={"PR_READY": 2, "READY": 3},
        expected_tasks=5,
        runs_count=1,
        paid_chief_calls=3,
        local_model_calls=2,
        pr_artifacts_logged=2,
        run_exit_code=0,
        routing_contract_summary={"chief_led": 3, "local_assisted": 2},
    )

    assert status == "PARTIAL"
    assert any("not PR_READY" in blocker for blocker in blockers)


def test_v4_benchmark_accepts_only_complete_pr_ready_run():
    from scripts.run_benchmark_v4_only import classify_benchmark_status

    status, blockers = classify_benchmark_status(
        preflight_failed=False,
        task_statuses={"PR_READY": 5},
        expected_tasks=5,
        runs_count=1,
        paid_chief_calls=3,
        local_model_calls=2,
        pr_artifacts_logged=5,
        run_exit_code=0,
        routing_contract_summary={"chief_led": 3, "local_assisted": 2},
    )

    assert status == "ACCEPTED"
    assert blockers == []


def test_v4_benchmark_requires_persisted_routing_contracts():
    from scripts.run_benchmark_v4_only import classify_benchmark_status

    status, blockers = classify_benchmark_status(
        preflight_failed=False,
        task_statuses={"PR_READY": 5},
        expected_tasks=5,
        runs_count=1,
        paid_chief_calls=3,
        local_model_calls=2,
        pr_artifacts_logged=5,
        run_exit_code=0,
        routing_contract_summary={},
    )

    assert status == "PARTIAL"
    assert any("routing contracts" in blocker for blocker in blockers)


def test_v4_routing_summary_ignores_invalid_metadata():
    from scripts.run_benchmark_v4_only import summarize_routing_contracts

    assert summarize_routing_contracts(
        [
            '{"task_contract":{"seniority_class":"chief_led"}}',
            {"task_contract": {"seniority_class": "chief_led"}},
            {"task_contract": {"seniority_class": "local_assisted"}},
            "not-json",
            None,
        ]
    ) == {"chief_led": 2, "local_assisted": 1}


def test_v4_benchmark_marks_blocked_needs_human_review_as_partial():
    """A run that escalates tasks to BLOCKED_NEEDS_HUMAN_REVIEW after the
    recovery budget is exhausted should be classified as PARTIAL rather
    than ACCEPTED, with an explicit blocker explaining which tasks were
    abandoned for human review."""
    from scripts.run_benchmark_v4_only import classify_benchmark_status

    status, blockers = classify_benchmark_status(
        preflight_failed=False,
        task_statuses={
            "PR_READY": 4,
            "BLOCKED_NEEDS_HUMAN_REVIEW": 1,
        },
        expected_tasks=5,
        runs_count=1,
        paid_chief_calls=3,
        local_model_calls=2,
        pr_artifacts_logged=4,
        run_exit_code=0,
        routing_contract_summary={"chief_led": 3, "local_assisted": 2},
    )

    assert status == "PARTIAL"
    assert any(
        "BLOCKED_NEEDS_HUMAN_REVIEW" in blocker for blocker in blockers
    )


def test_v4_benchmark_full_pr_ready_unaffected_by_recovery_loop():
    """Even when the scheduler's recovery loop has spare cycles left, a
    clean 100% PR_READY run still produces ACCEPTED."""
    from scripts.run_benchmark_v4_only import classify_benchmark_status

    status, blockers = classify_benchmark_status(
        preflight_failed=False,
        task_statuses={"PR_READY": 5},
        expected_tasks=5,
        runs_count=1,
        paid_chief_calls=3,
        local_model_calls=2,
        pr_artifacts_logged=5,
        run_exit_code=0,
        routing_contract_summary={
            "chief_led": 2,
            "local_assisted": 2,
            "chief_only": 1,
        },
    )

    assert status == "ACCEPTED"
    assert blockers == []
