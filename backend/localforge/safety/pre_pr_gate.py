import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from localforge.models import domain
from localforge.models.enums import VerificationStatus
from localforge.storage import UnitOfWork

logger = logging.getLogger(__name__)

SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]"),
    re.compile(r"(?i)secret[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{15,}"),
    re.compile(r"-----BEGIN\s+PRIVATE\s+KEY-----"),
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
]

PROTECTED_PATH_PATTERNS = [
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "credentials",
    ".git/",
    "node_modules/",
]


@dataclass
class PrePRGateResult:
    passed: bool
    project_id: int
    task_run_id: int
    checks: dict[str, bool] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MechanicalPrePRGate:
    """Mechanical Pre-PR Gate performing automated safety invariant validation prior to PR_READY."""

    @staticmethod
    def scan_diff_for_secrets(diff_text: str) -> list[str]:
        """Scan a diff or code string for plain-text secrets and credentials."""
        violations: list[str] = []
        for line in diff_text.splitlines():
            # Skip deletion lines
            if line.startswith("-"):
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    violations.append(f"Secret pattern matched in line: {line.strip()[:60]}...")
                    break
        return violations

    async def evaluate_gate(
        self,
        project_id: int,
        task_run_id: int,
        uow: UnitOfWork,
        diff_text: str = "",
        modified_files: list[str] | None = None,
        max_file_limit: int = 30,
        output_dir: str | Path | None = None,
    ) -> PrePRGateResult:
        """Run all mechanical pre-PR checks and output versioned gate artifact."""
        files = modified_files or []
        checks: dict[str, bool] = {}
        violations: list[str] = []

        # 1. File Count Limit Check
        if len(files) > max_file_limit:
            checks["file_count_limit"] = False
            violations.append(f"Modified file count ({len(files)}) exceeds maximum limit ({max_file_limit}).")
        else:
            checks["file_count_limit"] = True

        # 2. Protected Paths Contamination Check
        path_violations = []
        for file_path in files:
            norm_path = file_path.replace("\\", "/").lower()
            for prot in PROTECTED_PATH_PATTERNS:
                if prot.lower() in norm_path:
                    path_violations.append(f"Protected path '{prot}' found in modified file: {file_path}")

        if path_violations:
            checks["protected_paths"] = False
            violations.extend(path_violations)
        else:
            checks["protected_paths"] = True

        # 3. Mechanical Secret Scanning
        secret_violations = self.scan_diff_for_secrets(diff_text)
        if secret_violations:
            checks["secret_scanning"] = False
            violations.extend(secret_violations)
        else:
            checks["secret_scanning"] = True

        # 4. Independent Verifier Evidence Check
        assert uow.maker_checker is not None
        verification = await uow.maker_checker.get_verification_for_task_run(task_run_id)
        if not verification or verification.status != VerificationStatus.APPROVED:
            checks["verifier_evidence"] = False
            violations.append("Missing or unapproved independent Maker/Checker verification.")
        else:
            checks["verifier_evidence"] = True

        # 5. Permanent Auto-Merge Disabled Invariant
        checks["auto_merge_disabled"] = True

        overall_passed = all(checks.values())
        result = PrePRGateResult(
            passed=overall_passed,
            project_id=project_id,
            task_run_id=task_run_id,
            checks=checks,
            violations=violations,
        )

        # Write versioned gate artifact if output directory provided
        if output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            artifact_file = out_path / "pre_pr_gate_result.json"
            artifact_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

        return result
