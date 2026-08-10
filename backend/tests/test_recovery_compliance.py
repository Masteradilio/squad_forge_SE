from pathlib import Path

from scripts.run_recovery_compliance import run


def test_recovery_compliance_fixture_writes_accepted_evidence(tmp_path: Path):
    assert run(tmp_path) == 0
    report = (tmp_path / "recovery_compliance.json").read_text(encoding="utf-8")
    assert '"status": "PASS"' in report
    assert '"lease_recovered": true' in report

