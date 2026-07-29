"""Compliance evidence validation for V6 closure artifacts."""

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ACCEPTED = "ACCEPTED"
EVIDENCE_READY = "EVIDENCE_READY"
INVALID = "INVALID"


@dataclass(frozen=True)
class ComplianceEvidenceResult:
    verdict: str
    reasons: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.verdict == ACCEPTED


class ComplianceEvidenceValidator:
    """Validate immutable phase evidence without trusting authored verdicts."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def validate_manifest(self, manifest_path: Path) -> ComplianceEvidenceResult:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reasons: list[str] = []

        source_commit = str(manifest.get("source_commit", ""))
        if not source_commit or source_commit == "HEAD":
            reasons.append("source_commit must be an immutable commit, not HEAD or empty")
        elif not self._commit_exists(source_commit):
            reasons.append(f"source_commit does not exist: {source_commit}")

        parent_commit = manifest.get("parent_commit")
        if parent_commit and not self._commit_exists(str(parent_commit)):
            reasons.append(f"parent_commit does not exist: {parent_commit}")

        corpus_hash = str(manifest.get("corpus_hash") or manifest.get("manifest_hash") or "")
        if corpus_hash == EMPTY_SHA256:
            reasons.append("corpus hash must not be the SHA-256 of empty content")

        reasons.extend(self._validate_input_hashes(manifest))
        reasons.extend(self._validate_commands(manifest))

        requested_verdict = str(manifest.get("verdict", ""))
        if requested_verdict == ACCEPTED:
            reasons.extend(self._validate_accepted_release_fields(manifest))

        if reasons:
            return ComplianceEvidenceResult(verdict=INVALID, reasons=reasons)
        if self._has_accepted_release_fields(manifest):
            return ComplianceEvidenceResult(verdict=ACCEPTED)
        return ComplianceEvidenceResult(
            verdict=EVIDENCE_READY,
            reasons=["reviewed PR, merge commit, and CI evidence are still required for ACCEPTED"],
        )

    def _validate_input_hashes(self, manifest: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        input_hashes = manifest.get("input_hashes", {})
        if not isinstance(input_hashes, dict):
            return ["input_hashes must be an object when provided"]

        for raw_path, expected_hash in input_hashes.items():
            path = self.repo_root / str(raw_path)
            if not path.is_file():
                reasons.append(f"hashed input is missing: {raw_path}")
                continue
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                reasons.append(f"input hash mismatch for {raw_path}")
        return reasons

    def _validate_commands(self, manifest: dict[str, Any]) -> list[str]:
        commands = manifest.get("commands")
        if not isinstance(commands, list) or not commands:
            return ["manifest must include command evidence"]

        reasons: list[str] = []
        has_ruff = False
        for index, command in enumerate(commands):
            if not isinstance(command, dict):
                reasons.append(f"command evidence at index {index} must be an object")
                continue
            command_text = str(command.get("command", ""))
            if not command_text:
                reasons.append(f"command evidence at index {index} is missing command text")
            if not isinstance(command.get("exit_code"), int):
                reasons.append(f"command evidence at index {index} is missing integer exit_code")
            if "ruff" in command_text:
                has_ruff = True
        if str(manifest.get("verdict", "")) == ACCEPTED and not has_ruff:
            reasons.append("ACCEPTED evidence requires a Ruff command")
        if any(isinstance(cmd, dict) and cmd.get("exit_code") != 0 for cmd in commands):
            reasons.append("all mandatory commands must pass before acceptance")
        return reasons

    def _validate_accepted_release_fields(self, manifest: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        if not self._has_accepted_release_fields(manifest):
            reasons.append("ACCEPTED requires reviewed_pr_number, merge_commit, and ci_run_url")
            return reasons

        merge_commit = str(manifest["merge_commit"])
        if not self._commit_exists(merge_commit):
            reasons.append(f"merge_commit does not exist: {merge_commit}")
        if not manifest.get("human_reviewed", False):
            reasons.append("ACCEPTED requires human_reviewed: true")
        return reasons

    @staticmethod
    def _has_accepted_release_fields(manifest: dict[str, Any]) -> bool:
        return all(
            manifest.get(field_name)
            for field_name in ("reviewed_pr_number", "merge_commit", "ci_run_url")
        )

    def _commit_exists(self, commit: str) -> bool:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=self.repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
