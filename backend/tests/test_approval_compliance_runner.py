import json
from pathlib import Path

from scripts.run_approval_compliance import run


def test_approval_compliance_runner_proves_replay_expiry_and_tenant_boundary(tmp_path: Path):
    assert run(tmp_path) == 0
    report = json.loads((tmp_path / "approval_compliance.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["api_status"] == "PASS"
    assert report["cli_status"] == "PASS"
    assert report["cross_tenant_status"] == 404
    assert report["cli"]["tenant_id"] == "tenant-cli"
    assert report["cli"]["persisted"]["status"] == "APPROVED"
    assert report["cli"]["persisted"]["approver_id"] == "cli-auditor"
    assert report["cli"]["persisted"]["reason"] == "CLI compliance decision"
    assert report["cli"]["persisted"]["idempotency_key"] == "cli-approval-once-1"
    assert report["cli"]["persisted"]["audit_found"] is True
    assert report["cli"]["persisted"]["audit_count"] == 1
