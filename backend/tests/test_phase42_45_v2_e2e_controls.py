from pathlib import Path

from localforge.benchmark.v2 import BenchmarkRunManifest, BenchmarkV2Reporter
from localforge.models.enums import FailureClass
from localforge.visual.gate import VisualFidelityGate


def test_visual_gate_requires_rendered_evidence_for_visual_tasks(tmp_path):
    reference = tmp_path / "reference.png"
    actual = tmp_path / "actual.png"
    reference.write_bytes(b"fake-reference")
    actual.write_bytes(b"fake-actual")

    result = VisualFidelityGate().evaluate(
        reference_image_path=str(reference),
        actual_image_path=str(actual),
        task_is_visual=True,
    )

    assert result.passed is True
    assert result.failure_class is None
    assert result.metrics["actual_bytes"] == len(b"fake-actual")


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
