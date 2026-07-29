"""Compliance evidence validation for release artifacts."""

import hashlib
import json
import subprocess
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from localforge.services.file_hashes import stable_file_sha256
from localforge.version import RELEASE_TAG, VERSION

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ACCEPTED = "ACCEPTED"
EVIDENCE_READY = "EVIDENCE_READY"
INVALID = "INVALID"
DISPUTED = "DISPUTED"
V62_CANDIDATE_SCHEMA = "localforge.v6_2.candidate_manifest.v1"
V62_FINAL_SCHEMA = "localforge.v6_2.final_manifest.v1"
SUPPORTED_V62_SCHEMAS = {V62_CANDIDATE_SCHEMA, V62_FINAL_SCHEMA}


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def manifest_sha256(payload: dict[str, Any]) -> str:
    comparable = deepcopy(payload)
    comparable.pop("manifest_sha256", None)
    comparable.pop("checksum_sha256", None)
    return hashlib.sha256(canonical_json_bytes(comparable)).hexdigest()


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

        schema_values = [
            str(manifest.get(field_name, ""))
            for field_name in ("schema_version", "artifact_schema")
            if manifest.get(field_name)
        ]
        if any(schema_version.startswith("localforge.v6_1.") for schema_version in schema_values):
            reasons.append("historical V6.1 evidence is disputed and cannot be ACCEPTED")
        elif not schema_values:
            reasons.append("manifest must declare schema_version or artifact_schema")
        elif not any(schema_version in SUPPORTED_V62_SCHEMAS for schema_version in schema_values):
            reasons.append("manifest must use the canonical V6.2 evidence schema")

        manifest_version = str(manifest.get("release_version") or manifest.get("target_release") or "")
        if manifest_version and manifest_version not in {VERSION, f"V{VERSION}"}:
            reasons.append(f"manifest release version {manifest_version} does not match canonical version {VERSION}")

        release_tag = str(manifest.get("release_tag", ""))
        if release_tag and release_tag != RELEASE_TAG:
            reasons.append(f"manifest release_tag {release_tag} does not match canonical tag {RELEASE_TAG}")

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

        reasons.extend(self._validate_manifest_checksum(manifest))
        reasons.extend(self._validate_input_hashes(manifest))
        reasons.extend(self._validate_commands(manifest))

        if self._has_synthetic_observations(manifest):
            reasons.append("manifest contains synthetic benchmark observations")

        requested_verdict = str(manifest.get("verdict", ""))
        if requested_verdict == ACCEPTED:
            reasons.extend(self._validate_mandatory_phase_status(manifest))
            if V62_FINAL_SCHEMA not in schema_values:
                reasons.append("ACCEPTED requires the canonical final V6.2 evidence schema")
            reasons.extend(self._validate_accepted_release_fields(manifest))
            reasons.extend(self._validate_github_metadata(manifest))

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
            candidate_path = Path(str(raw_path))
            path = candidate_path if candidate_path.is_absolute() else self.repo_root / candidate_path
            if not path.is_file():
                reasons.append(f"hashed input is missing: {raw_path}")
                continue
            actual_hash = stable_file_sha256(path)
            if actual_hash != expected_hash:
                reasons.append(f"input hash mismatch for {raw_path}")
        return reasons

    def _validate_manifest_checksum(self, manifest: dict[str, Any]) -> list[str]:
        expected = manifest.get("manifest_sha256") or manifest.get("checksum_sha256")
        if expected is None:
            return []
        if not isinstance(expected, str) or len(expected) != 64:
            return ["manifest checksum must be a SHA-256 hex string"]
        actual = manifest_sha256(manifest)
        if expected != actual:
            return ["manifest checksum mismatch"]
        return []

    @staticmethod
    def _validate_mandatory_phase_status(manifest: dict[str, Any]) -> list[str]:
        phases = manifest.get("mandatory_phases")
        if phases is None:
            return ["ACCEPTED requires mandatory phase status evidence"]

        incomplete: list[str] = []
        if isinstance(phases, dict):
            for phase_name, status in phases.items():
                if status != ACCEPTED:
                    incomplete.append(str(phase_name))
        elif isinstance(phases, list):
            for index, phase in enumerate(phases):
                if not isinstance(phase, dict):
                    incomplete.append(f"index {index}")
                    continue
                phase_name = str(phase.get("phase") or phase.get("name") or f"index {index}")
                if phase.get("status") != ACCEPTED and phase.get("verdict") != ACCEPTED:
                    incomplete.append(phase_name)
        else:
            return ["mandatory_phases must be an object or list"]

        if incomplete:
            return [f"mandatory phases are incomplete: {', '.join(incomplete)}"]
        return []

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
            reasons.append("ACCEPTED requires reviewed_pr_number, merge_commit, ci_run_url, human_reviewed, and release_tag")
            return reasons

        merge_commit = str(manifest["merge_commit"])
        if not self._commit_exists(merge_commit):
            reasons.append(f"merge_commit does not exist: {merge_commit}")
        if not manifest.get("human_reviewed", False):
            reasons.append("ACCEPTED requires human_reviewed: true")
        reviewed_pr_number = manifest.get("reviewed_pr_number")
        if not isinstance(reviewed_pr_number, int) or reviewed_pr_number <= 0:
            reasons.append("ACCEPTED requires a positive integer reviewed_pr_number")
        if not str(manifest.get("ci_run_url", "")).startswith("https://github.com/"):
            reasons.append("ACCEPTED requires a GitHub Actions ci_run_url")
        if str(manifest.get("release_tag", "")) != RELEASE_TAG:
            reasons.append(f"ACCEPTED requires release_tag {RELEASE_TAG}")
        return reasons

    def _validate_github_metadata(self, manifest: dict[str, Any]) -> list[str]:
        metadata = manifest.get("github_metadata")
        if not isinstance(metadata, dict):
            return ["ACCEPTED requires trusted github_metadata"]

        reasons: list[str] = []
        reviewed_pr_number = manifest.get("reviewed_pr_number")
        if metadata.get("pr_number") != reviewed_pr_number:
            reasons.append("github_metadata.pr_number must match reviewed_pr_number")
        if metadata.get("merge_commit") != manifest.get("merge_commit"):
            reasons.append("github_metadata.merge_commit must match merge_commit")
        if metadata.get("head_commit") != manifest.get("source_commit"):
            reasons.append("github_metadata.head_commit must match source_commit")
        if metadata.get("ci_run_url") != manifest.get("ci_run_url"):
            reasons.append("github_metadata.ci_run_url must match ci_run_url")
        if metadata.get("ci_conclusion") != "success":
            reasons.append("github_metadata.ci_conclusion must be success")
        if metadata.get("direct_to_main") is True:
            reasons.append("direct-to-main implementation cannot be reviewed PR evidence")
        if metadata.get("human_reviewed") is not True:
            reasons.append("github_metadata.human_reviewed must be true")
        if metadata.get("reviewer_login") and metadata.get("reviewer_login") == metadata.get("author_login"):
            reasons.append("self-review cannot satisfy human review evidence")
        if metadata.get("release_tag") != manifest.get("release_tag"):
            reasons.append("github_metadata.release_tag must match release_tag")
        return reasons

    @staticmethod
    def _has_accepted_release_fields(manifest: dict[str, Any]) -> bool:
        return all(
            manifest.get(field_name)
            for field_name in ("reviewed_pr_number", "merge_commit", "ci_run_url", "release_tag")
        )

    @staticmethod
    def _has_synthetic_observations(manifest: dict[str, Any]) -> bool:
        observations = manifest.get("observations") or manifest.get("benchmark_observations")
        if not isinstance(observations, list):
            return False
        for observation in observations:
            if isinstance(observation, dict) and observation.get("synthetic") is True:
                return True
        return False

    def _commit_exists(self, commit: str) -> bool:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=self.repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
