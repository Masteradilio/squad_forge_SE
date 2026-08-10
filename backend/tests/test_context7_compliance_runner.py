from pathlib import Path

from scripts.run_context7_compliance import run


def test_context7_task_decision_runner_writes_evidence(tmp_path: Path):
    assert run(tmp_path) == 0
    report = (tmp_path / "context7_decision.json").read_text(encoding="utf-8")
    assert '"event": "context7.decision_recorded"' in report
    assert '"status": "PASS"' in report

