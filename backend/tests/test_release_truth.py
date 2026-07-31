import ast
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

import scripts.check_release_truth as release_truth


def test_release_truth_script_passes_current_repository() -> None:
    report = release_truth.build_report(Path.cwd())
    historical_manifest = cast(dict[str, Any], report["historical_v61_manifest"])
    backlog = cast(dict[str, Any], report["backlog"])
    audit_of_audit = cast(dict[str, Any], report["audit_of_audit"])
    release_identity = cast(dict[str, Any], report["release_identity"])

    assert report["passed"] is True
    assert historical_manifest["verdict"] == "INVALID"
    assert backlog["unresolved_checkbox_count"] >= 0
    assert backlog["phase_status"]
    assert report["accepted_final_manifests"] == []
    assert audit_of_audit["passed"] is True
    assert audit_of_audit["missing_ids"] == []
    assert audit_of_audit["missing_sections"] == []
    assert release_identity["passed"] is True
    assert release_identity["missing_fragments"] == []


def test_release_truth_requires_audit_of_audit_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "audit_of_audit.md"
    report_path.write_text("AOA-01 only\n", encoding="utf-8")
    monkeypatch.setattr(release_truth, "AOA_REPORT", Path("audit_of_audit.md"))

    status = release_truth.audit_of_audit_status(tmp_path)
    missing_ids = cast(list[str], status["missing_ids"])
    missing_sections = cast(list[str], status["missing_sections"])

    assert status["passed"] is False
    assert "AOA-12" in missing_ids
    assert "## AOA Findings Matrix" in missing_sections


def test_release_truth_reports_backlog_status_by_phase(tmp_path: Path) -> None:
    backlog = tmp_path / "backlog.md"
    backlog.write_text(
        "\n".join(
            [
                "# Test backlog",
                "",
                "## Phase R0 - First",
                "- [x] done",
                "- [ ] open",
                "",
                "## Phase R1 - Second",
                "- [x] done",
            ]
        ),
        encoding="utf-8",
    )

    status = release_truth.phase_backlog_status(backlog)

    assert status == [
        {
            "heading": "Phase R0 - First",
            "line": 3,
            "open": 1,
            "closed": 1,
            "total": 2,
            "status": "OPEN",
        },
        {
            "heading": "Phase R1 - Second",
            "line": 7,
            "open": 0,
            "closed": 1,
            "total": 1,
            "status": "CHECKBOXES_CLOSED",
        },
    ]


def test_release_truth_requires_release_identity_conventions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity_path = tmp_path / "release_identity.md"
    identity_path.write_text("Product version: `6.2.0`\n", encoding="utf-8")
    monkeypatch.setattr(release_truth, "RELEASE_IDENTITY", Path("release_identity.md"))

    status = release_truth.release_identity_status(tmp_path)
    missing = cast(list[str], status["missing_fragments"])

    assert status["passed"] is False
    assert "Candidate evidence verdict: `EVIDENCE_READY`" in missing


def test_demo_guide_references_existing_sample_project() -> None:
    guide = Path("docs/demo.md").read_text(encoding="utf-8")

    assert "samples/demo-project" not in guide
    assert Path("samples/demo-lf-smoke-prd/PRD.md").is_file()
    assert "localforge import-prd PRD.md" in guide


def test_pr_ready_status_transition_has_single_server_owned_writer() -> None:
    service_source = Path("backend/localforge/services/task.py").read_text(encoding="utf-8")
    assert service_source.count("async def mark_pr_ready(") == 1
    assert service_source.count("TaskStatus.PR_READY, allow_pr_ready=True") == 1

    offenders: list[str] = []
    ignored = {
        Path("backend/localforge/models/enums.py"),
        Path("backend/localforge/services/task.py"),
        Path("backend/localforge/demo.py"),
    }
    for path in sorted(Path("backend/localforge").rglob("*.py")):
        if path in ignored:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _is_update_task_status_to_pr_ready(node):
                offenders.append(f"{path}:update_task_status")
            if _is_status_assignment_to_pr_ready(node):
                offenders.append(f"{path}:status-assignment")

    assert offenders == []


def _is_update_task_status_to_pr_ready(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "update_task_status":
        return False
    return any(_is_task_status_pr_ready(arg) for arg in node.args) or any(
        _is_task_status_pr_ready(keyword.value) for keyword in node.keywords
    )


def _is_status_assignment_to_pr_ready(node: ast.AST) -> bool:
    targets: list[ast.expr]
    value: ast.expr
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
        value = node.value
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
        if node.value is None:
            return False
        value = node.value
    else:
        return False
    if not _is_task_status_pr_ready(value):
        return False
    return any(isinstance(target, ast.Attribute) and target.attr == "status" for target in targets)


def _is_task_status_pr_ready(node: ast.AST) -> bool:
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "PR_READY"
        and isinstance(node.value, ast.Name)
        and node.value.id == "TaskStatus"
    ):
        return True
    return isinstance(node, ast.Constant) and node.value == "PR_READY"


def test_release_truth_detects_stable_claim_leak(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "claim.md").write_text(
        "This is a supervised-production-ready stable release.\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "docs/claim.md")
    _git(tmp_path, "commit", "-m", "claim")

    leaks = release_truth.stable_claim_leaks(tmp_path)

    assert leaks == [{"path": "docs/claim.md", "line": 1}]


def test_release_truth_detects_accepted_final_manifest_with_open_backlog(tmp_path: Path) -> None:
    (tmp_path / "docs" / "e2e" / "release").mkdir(parents=True)
    manifest_path = tmp_path / "docs" / "e2e" / "release" / "final_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "localforge.v6_2.final_manifest.v1",
                "verdict": "ACCEPTED",
            }
        ),
        encoding="utf-8",
    )

    accepted = release_truth.accepted_final_manifests(tmp_path)

    assert accepted == [{"path": "docs/e2e/release/final_manifest.json"}]


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.local")
    _git(path, "config", "user.name", "Test User")


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
