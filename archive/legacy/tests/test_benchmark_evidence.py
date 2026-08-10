import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "collect_benchmark_evidence.py"
SPEC = importlib.util.spec_from_file_location("benchmark_evidence", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark_evidence)


def test_collects_generic_lane_manifest(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    prd = tmp_path / "prd.md"
    prd.write_text("# Unseen task\n", encoding="utf-8")
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "acceptance_passed": True,
                "elapsed_seconds": 12.5,
                "retries": 1,
                "human_interventions": 0,
                "model_calls": 4,
                "paid_cost_usd": 0.12,
                "local_inference_seconds": 8.1,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "evidence" / "hybrid.json"

    exit_code = benchmark_evidence.main(
        [
            "--lane",
            "hybrid",
            "--workspace",
            str(workspace),
            "--prd",
            str(prd),
            "--metrics",
            str(metrics),
            "--acceptance-command",
            "python -m pytest acceptance_tests -q",
            "--output",
            str(output),
        ]
    )

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert manifest["lane"] == "hybrid"
    assert manifest["evidence_status"] == "COLLECTED_NOT_EVALUATED"
    assert manifest["metrics"]["paid_cost_usd"] == 0.12
    assert manifest["workspace"]["git"]["commit"] is None
