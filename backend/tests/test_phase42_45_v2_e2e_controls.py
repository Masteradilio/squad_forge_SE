from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from localforge.benchmark.v2 import BenchmarkRunManifest, BenchmarkV2Reporter
from localforge.models import domain
from localforge.models.enums import FailureClass
from localforge.pipeline.engine import RolePipelineEngine
from localforge.pr_factory.local import LocalPRFactory
from localforge.visual.gate import VisualFidelityGate


def test_visual_gate_requires_rendered_evidence_for_visual_tasks(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    reference = tmp_path / "reference.png"
    actual = tmp_path / "actual.png"
    Image.new("RGB", (100, 100), color="white").save(reference)
    Image.new("RGB", (100, 100), color="white").save(actual)

    result = VisualFidelityGate().evaluate(
        reference_image_path=str(reference),
        actual_image_path=str(actual),
        task_is_visual=True,
    )

    assert result.passed is True
    assert result.failure_class is None
    assert result.metrics["actual_bytes"] == actual.stat().st_size


def test_visual_gate_blocks_missing_actual_image(tmp_path):
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"fake-reference")

    result = VisualFidelityGate().evaluate(
        reference_image_path=str(reference),
        actual_image_path=str(tmp_path / "missing.png"),
        task_is_visual=True,
    )

    assert result.passed is False
    assert result.failure_class == FailureClass.VISUAL_MISMATCH
    assert "missing" in result.summary.lower()


def test_visual_gate_blocks_missing_reference_for_visual_tasks(tmp_path):
    actual = tmp_path / "actual.png"
    actual.write_bytes(b"fake-actual")

    result = VisualFidelityGate().evaluate(
        reference_image_path=str(tmp_path / "missing-reference.png"),
        actual_image_path=str(actual),
        task_is_visual=True,
    )

    assert result.passed is False
    assert result.failure_class == FailureClass.VISUAL_MISMATCH
    assert "reference" in result.summary.lower()


def test_visual_gate_checks_aspect_ratio_mismatch(tmp_path):
    # Testing ref 100x100 (ratio 1.0) and actual 100x200 (ratio 0.5)
    # Difference is 0.5/1.0 = 50% which is > 15% threshold
    try:
        from PIL import Image

        ref = tmp_path / "ref.png"
        act = tmp_path / "act.png"
        Image.new("RGB", (100, 100)).save(ref)
        Image.new("RGB", (100, 200)).save(act)

        result = VisualFidelityGate().evaluate(
            reference_image_path=str(ref),
            actual_image_path=str(act),
            task_is_visual=True,
        )
        assert result.passed is False
        assert result.failure_class == FailureClass.VISUAL_MISMATCH
        assert "aspect ratio mismatch" in result.summary.lower()
    except ImportError:
        # Fallback if Pillow is not fully ready in test context
        pass


def test_benchmark_reporter_rates_funciona_bem_only_when_thresholds_pass(tmp_path):
    manifest = BenchmarkRunManifest(
        name="hp12c-v2",
        task_count=31,
        pr_ready_count=31,
        failed_safe_count=0,
        blocked_count=0,
        human_interventions=0,
        paid_calls=3,
        estimated_cost_usd=0.015,
        repair_attempts=2,
        failure_classes={},
        wall_clock_seconds=1200.0,
        integration_passed=True,
        visual_passed=True,
        acceptance_scenarios_passed=5,
        acceptance_scenarios_total=5,
    )

    report = BenchmarkV2Reporter().render(manifest)

    assert report.rating == "Funciona bem"
    assert "paid_calls: 3" in report.markdown


def test_benchmark_reporter_records_hp12c_v2_blockers(tmp_path):
    manifest = BenchmarkRunManifest(
        name="hp12c-v2",
        task_count=31,
        pr_ready_count=20,
        failed_safe_count=11,
        blocked_count=0,
        human_interventions=0,
        paid_calls=5,
        estimated_cost_usd=0.04,
        repair_attempts=9,
        failure_classes={"SEMANTIC_TEST_FAILURE": 8},
        wall_clock_seconds=1800.0,
        integration_passed=False,
        visual_passed=True,
        acceptance_scenarios_passed=4,
        acceptance_scenarios_total=5,
    )
    output_path = Path(tmp_path) / "report.md"

    report = BenchmarkV2Reporter().write_report(manifest, str(output_path))

    assert report.rating == "Funciona com ressalvas"
    assert "integration_passed: False" in output_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_local_pr_factory_runs_contract_verifier_when_contract_exists():
    uow = MagicMock()
    uow.projects = AsyncMock()
    uow.tasks = AsyncMock()
    uow.audits = AsyncMock()

    project = domain.Project(id=1, name="Test", root_path=".", default_branch="main")
    task = domain.Task(
        id=2,
        project_id=1,
        key="LF-101",
        title="Task title",
        description="desc",
        metadata={"task_contract": {"allowed_files": ["core.py"]}},
    )
    task_run = domain.TaskRun(id=3, run_id=10, task_id=2, branch_name="feat-101", worktree_path=".")

    uow.projects.get_project.return_value = project
    uow.tasks.get_task.return_value = task
    uow.tasks.get_task_run.return_value = task_run
    uow.audits.list_artifacts_for_task_run.return_value = []

    with patch("localforge.pr_factory.local.ContractVerifier") as MockVerifier:
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = MagicMock(
            passed=False, findings=[MagicMock(message="Forbidden scipy")]
        )
        MockVerifier.return_value = mock_verifier

        factory = LocalPRFactory(uow, project_id=1, run_id=10)
        result = await factory.generate(task_id=2, task_run_id=3)

        assert result.ready is False
        assert any("Contract violation: Forbidden scipy" in r for r in result.reasons)
        mock_verifier.verify.assert_called_once()


@pytest.mark.asyncio
async def test_local_pr_factory_runs_visual_gate_only_when_visual_required():
    uow = MagicMock()
    uow.projects = AsyncMock()
    uow.tasks = AsyncMock()
    uow.audits = AsyncMock()

    project = domain.Project(id=1, name="Test", root_path=".", default_branch="main")
    task_no_visual = domain.Task(
        id=2,
        project_id=1,
        key="LF-101",
        title="Task title",
        description="desc",
        metadata={"task_contract": {"allowed_files": ["core.py"]}},
    )
    task_run = domain.TaskRun(id=3, run_id=10, task_id=2, branch_name="feat-101", worktree_path=".")

    uow.projects.get_project.return_value = project
    uow.tasks.get_task.return_value = task_no_visual
    uow.tasks.get_task_run.return_value = task_run
    uow.audits.list_artifacts_for_task_run.return_value = []

    with (
        patch("localforge.pr_factory.local.capture_html_screenshot") as mock_screenshot,
        patch("localforge.pr_factory.local.VisualFidelityGate") as MockVisualGate,
    ):
        factory = LocalPRFactory(uow, project_id=1, run_id=10)
        result = await factory.generate(task_id=2, task_run_id=3)

        mock_screenshot.assert_not_called()
        MockVisualGate.assert_not_called()

    task_visual = domain.Task(
        id=2,
        project_id=1,
        key="LF-101",
        title="Task title",
        description="desc",
        metadata={
            "visual_required": True,
            "visual_reference_image": "ref.png",
            "visual_actual_output": "index.html",
        },
    )
    uow.tasks.get_task.return_value = task_visual

    with (
        patch("localforge.pr_factory.local.capture_html_screenshot") as mock_screenshot,
        patch("localforge.pr_factory.local.VisualFidelityGate") as MockVisualGate,
        patch("os.path.isfile", return_value=True),
    ):
        mock_screenshot.return_value = True
        mock_gate = MagicMock()
        mock_gate.evaluate.return_value = MagicMock(
            passed=False, summary="Visual similarity below threshold: 0.80"
        )
        MockVisualGate.return_value = mock_gate

        factory = LocalPRFactory(uow, project_id=1, run_id=10)
        result = await factory.generate(task_id=2, task_run_id=3)

        assert result.ready is False
        assert any(
            "Visual mismatch: Visual similarity below threshold: 0.80" in r for r in result.reasons
        )
        mock_screenshot.assert_called_once()
        mock_gate.evaluate.assert_called_once()


@pytest.mark.asyncio
async def test_visual_task_sanitizer_does_not_replace_broken_tests_with_placeholder(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_ui_buttons.py"
    test_file.write_text("def test_buttons():\n    assert True\n  bad_indent\n", encoding="utf-8")

    task = domain.Task(
        id=2,
        project_id=1,
        key="LF-PRD-004",
        title="Dashboard controls",
        description="Visual task",
        metadata={"task_contract": {"visual_required": True}},
    )
    task_run = domain.TaskRun(id=3, run_id=10, task_id=2, worktree_path=str(tmp_path))

    engine = RolePipelineEngine(MagicMock(), project_id=1, run_id=10)
    await engine._sanitize_generated_python_files(
        editor=MagicMock(),
        task=task,
        task_run=task_run,
        changed_files=["tests/test_ui_buttons.py"],
    )

    assert test_file.read_text(encoding="utf-8") != "def test_placeholder():\n    assert True\n"


@pytest.mark.asyncio
async def test_chief_engineer_receives_expanded_visual_file_context(tmp_path):
    html = tmp_path / "app" / "dashboard.html"
    html.parent.mkdir()
    html.write_text("<button>1</button>\n" + ("x" * 15_000), encoding="utf-8")

    task = domain.Task(
        id=2,
        project_id=1,
        key="LF-PRD-004",
        title="Dashboard controls",
        description="Visual task",
        metadata={
            "task_contract": {
                "visual_required": True,
                "allowed_files": ["app/dashboard.html"],
            }
        },
    )
    task_run = domain.TaskRun(id=3, run_id=10, task_id=2, worktree_path=str(tmp_path))
    captured: dict[str, str] = {}

    class EmptyPlan:
        def runtime_actions(self):
            return []

    async def fake_plan_semantic_repair(**kwargs):
        captured["context"] = kwargs["changed_files_context"]
        return EmptyPlan()

    config = SimpleNamespace(
        chief_engineer=SimpleNamespace(
            enabled=True,
            provider="openrouter",
            model="minimax/minimax-m3",
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            fallback_provider=None,
            fallback_model=None,
            fallback_api_key=None,
        )
    )

    with (
        patch("localforge.pipeline.engine.load_config", return_value=config),
        patch("localforge.pipeline.engine.build_chief_engineer_provider"),
        patch("localforge.pipeline.engine.ChiefEngineerService") as service_cls,
    ):
        service_cls.return_value.plan_semantic_repair = fake_plan_semantic_repair
        engine = RolePipelineEngine(MagicMock(), project_id=1, run_id=10)
        repaired = await engine._try_chief_engineer_repair(
            task=task,
            task_run=task_run,
            context=MagicMock(),
            editor=MagicMock(),
            changed_files=["app/dashboard.html"],
            command_summaries=[],
            validation_output="Visual validation failed",
        )

    assert repaired is False
    assert "app/dashboard.html" in captured["context"]
    assert len(captured["context"]) > 12_000
