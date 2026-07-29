import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import localforge
from localforge.services.compliance_evidence import (
    ACCEPTED,
    EMPTY_SHA256,
    EVIDENCE_READY,
    INVALID,
    ComplianceEvidenceValidator,
)


def _head_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_manifest(source_commit: str) -> dict[str, object]:
    return {
        "schema_version": "v6-compliance-manifest-1",
        "phase": "phase_C0",
        "task_ids": ["V6C-004"],
        "source_commit": source_commit,
        "commands": [
            {
                "command": "python -m pytest backend/tests/test_compliance_evidence.py -q",
                "exit_code": 0,
            },
            {
                "command": (
                    "python -m ruff check backend/localforge/services/compliance_evidence.py"
                ),
                "exit_code": 0,
            },
        ],
    }


def test_compliance_evidence_rejects_head_and_nonexistent_commit(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _base_manifest("HEAD"))

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == INVALID
    assert any("not HEAD" in reason for reason in result.reasons)

    manifest = _base_manifest("0" * 40)
    _write_manifest(manifest_path, manifest)

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == INVALID
    assert any("does not exist" in reason for reason in result.reasons)


def test_compliance_evidence_rejects_empty_or_mismatched_hash(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    tracked_input = tmp_path / "input.txt"
    tracked_input.write_text("actual", encoding="utf-8")
    manifest = _base_manifest(_head_commit())
    manifest["corpus_hash"] = EMPTY_SHA256
    manifest["input_hashes"] = {str(tracked_input): hashlib.sha256(b"expected").hexdigest()}
    _write_manifest(manifest_path, manifest)

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == INVALID
    assert any("empty content" in reason for reason in result.reasons)
    assert any("input hash mismatch" in reason for reason in result.reasons)


def test_compliance_evidence_prevents_manual_accepted_override(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = _base_manifest(_head_commit())
    manifest["verdict"] = ACCEPTED
    _write_manifest(manifest_path, manifest)

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == INVALID
    assert any("reviewed_pr_number" in reason for reason in result.reasons)


def test_compliance_evidence_rejects_historical_v61_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = _base_manifest(_head_commit())
    manifest.update(
        {
            "artifact_schema": "localforge.v6_1.compliance_manifest.v1",
            "verdict": ACCEPTED,
            "release_tag": "v6.1.0",
            "reviewed_pr_number": 1,
            "merge_commit": _head_commit(),
            "ci_run_url": "https://github.com/Masteradilio/local_forge_os/actions/runs/1",
            "human_reviewed": True,
        }
    )
    _write_manifest(manifest_path, manifest)

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == INVALID
    assert any("historical V6.1 evidence is disputed" in reason for reason in result.reasons)
    assert any("release_tag v6.1.0 does not match canonical tag v6.2.0" in reason for reason in result.reasons)


def test_compliance_evidence_rejects_synthetic_benchmark_observations(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = _base_manifest(_head_commit())
    manifest["observations"] = [{"task_key": "LF-1", "synthetic": True, "tokens": 10}]
    _write_manifest(manifest_path, manifest)

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == INVALID
    assert any("synthetic benchmark" in reason for reason in result.reasons)


def test_compliance_evidence_accepts_immutable_fixture(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    commit = _head_commit()
    manifest = _base_manifest(commit)
    manifest.update(
        {
            "verdict": ACCEPTED,
            "release_version": "6.2.0",
            "release_tag": "v6.2.0",
            "reviewed_pr_number": 13,
            "merge_commit": commit,
            "ci_run_url": "https://github.com/Masteradilio/local_forge_os/actions/runs/1",
            "human_reviewed": True,
        }
    )
    _write_manifest(manifest_path, manifest)

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == ACCEPTED
    assert result.accepted is True


def test_compliance_evidence_without_review_is_evidence_ready(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _base_manifest(_head_commit()))

    result = ComplianceEvidenceValidator(Path.cwd()).validate_manifest(manifest_path)

    assert result.verdict == EVIDENCE_READY


def test_product_version_is_canonical_across_backend_and_frontend() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    frontend_package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))
    frontend_lock = json.loads(Path("frontend/package-lock.json").read_text(encoding="utf-8"))

    assert localforge.__version__ == "6.2.0"
    assert pyproject["project"]["version"] == localforge.__version__
    assert frontend_package["version"] == localforge.__version__
    assert frontend_lock["version"] == localforge.__version__
    assert frontend_lock["packages"][""]["version"] == localforge.__version__


def test_compliance_evidence_import_has_no_service_storage_cycle() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from localforge.services.compliance_evidence import ComplianceEvidenceValidator; print(ComplianceEvidenceValidator.__name__)",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ComplianceEvidenceValidator"
