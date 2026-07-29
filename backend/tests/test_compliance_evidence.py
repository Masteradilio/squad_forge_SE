import hashlib
import json
import subprocess
from pathlib import Path

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


def test_compliance_evidence_accepts_immutable_fixture(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    commit = _head_commit()
    manifest = _base_manifest(commit)
    manifest.update(
        {
            "verdict": ACCEPTED,
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
