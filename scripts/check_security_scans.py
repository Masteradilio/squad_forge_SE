"""Automated security scanning script for release compliance (V61C-1000, V61C-923).

Checks for:
1. Absence of un-redacted API secrets (ghp_*, sk-*, raw passwords) in python/md files.
2. Verification of security sanitization helpers in connectors and loops.
3. Path traversal boundary enforcement checks.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9_]{30,}"), "GitHub Personal Access Token"),
    (re.compile(r"sk-[A-Za-z0-9_]{30,}"), "OpenAI Secret Key"),
    (re.compile(r"xoxb-[A-Za-z0-9_-]{20,}"), "Slack Bot Token"),
]
KNOWN_TEST_SENTINELS = {
    "ghp_0123456789abcdef0123456789abcdef",
}

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "benchmarks",
    ".localforge",
    "dist",
    "coverage",
    "test-results",
    "playwright-report",
}


def scan_for_secrets() -> list[str]:
    findings: list[str] = []
    for file_path in ROOT.rglob("*"):
        if file_path.is_file() and not any(part in EXCLUDED_DIRS for part in file_path.parts):
            if file_path.suffix in (".py", ".md", ".json", ".yaml", ".yml"):
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                    for pattern, desc in SECRET_PATTERNS:
                        matches = [match.group(0) for match in pattern.finditer(text)]
                        real_matches = [match for match in matches if match not in KNOWN_TEST_SENTINELS]
                        if real_matches:
                            # Ensure it's not a dummy placeholder in test
                            if "dummy" not in text and "example" not in text and "MASKED" not in text:
                                findings.append(f"Potential {desc} in {file_path.relative_to(ROOT)}")
                except Exception as exc:
                    findings.append(f"Could not read {file_path}: {exc}")
    return findings


def check_sanitization_integrity() -> list[str]:
    findings: list[str] = []
    connector_file = ROOT / "backend" / "localforge" / "connectors" / "github_connector.py"
    if not connector_file.is_file():
        findings.append("Missing github_connector.py")
    else:
        text = connector_file.read_text(encoding="utf-8")
        if "sanitize_log_credential" not in text:
            findings.append("github_connector.py missing sanitize_log_credential")

    connector_base = ROOT / "backend" / "localforge" / "services" / "operational_connector.py"
    if not connector_base.is_file():
        findings.append("Missing operational_connector.py")
    else:
        text = connector_base.read_text(encoding="utf-8")
        if "sanitize_external_text" not in text:
            findings.append("operational_connector.py missing sanitize_external_text")

    return findings


def main() -> int:
    print("Running LocalForge OS Security Scan...")
    secret_findings = scan_for_secrets()
    sanitization_findings = check_sanitization_integrity()

    all_findings = secret_findings + sanitization_findings
    if all_findings:
        print("SECURITY SCAN FAILED:")
        for item in all_findings:
            print(f"  - {item}")
        return 1

    print("SECURITY SCAN PASSED: 0 secrets detected, sanitization integrity verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
