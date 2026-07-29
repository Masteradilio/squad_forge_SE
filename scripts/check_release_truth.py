from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from localforge.services.compliance_evidence import ACCEPTED, INVALID, ComplianceEvidenceValidator  # noqa: E402

BACKLOG_PATH = Path("docs/compliance_backlog_V6-1.md")
HISTORICAL_V61_MANIFEST = Path("docs/e2e/v6_1_compliance/manifest.json")
FORBIDDEN_STABLE_PHRASE = "supervised-production-ready stable release"
STABLE_PHRASE_ALLOWLIST = {
    "docs/compliance_backlog_V6.md",
    "docs/compliance_backlog_V6-1.md",
}


def open_backlog_checkboxes(backlog_path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line_number, line in enumerate(backlog_path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("- [ ]"):
            entries.append({"line": line_number, "text": line.strip()})
    return entries


def tracked_text_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    suffixes = {".json", ".md", ".rst", ".toml", ".txt", ".yaml", ".yml"}
    return [
        root / raw_path
        for raw_path in result.stdout.splitlines()
        if raw_path and Path(raw_path).suffix.lower() in suffixes and (root / raw_path).is_file()
    ]


def stable_claim_leaks(root: Path) -> list[dict[str, object]]:
    leaks: list[dict[str, object]] = []
    for path in tracked_text_paths(root):
        relative = path.relative_to(root).as_posix()
        if relative in STABLE_PHRASE_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_STABLE_PHRASE in line:
                leaks.append({"path": relative, "line": line_number})
    return leaks


def accepted_final_manifests(root: Path) -> list[dict[str, object]]:
    accepted: list[dict[str, object]] = []
    for manifest_path in sorted((root / "docs" / "e2e").glob("**/*.json")):
        try:
            payload: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if payload.get("schema_version") == "localforge.v6_2.final_manifest.v1" and payload.get("verdict") == ACCEPTED:
            accepted.append({"path": manifest_path.relative_to(root).as_posix()})
    return accepted


def build_report(root: Path) -> dict[str, object]:
    validator = ComplianceEvidenceValidator(root)
    backlog_path = root / BACKLOG_PATH
    v61_result = validator.validate_manifest(root / HISTORICAL_V61_MANIFEST)
    unresolved = open_backlog_checkboxes(backlog_path)
    final_accepted = accepted_final_manifests(root)
    phrase_leaks = stable_claim_leaks(root)

    findings: list[str] = []
    if v61_result.verdict != INVALID:
        findings.append("historical V6.1 manifest must remain INVALID under the canonical validator")
    if unresolved and final_accepted:
        findings.append("final ACCEPTED manifests are forbidden while the compliance backlog has unresolved tasks")
    if phrase_leaks:
        findings.append("stable production claim phrase appears outside allowed backlog documents")

    return {
        "schema_version": "localforge.v6_2.release_truth_check.v1",
        "passed": not findings,
        "findings": findings,
        "historical_v61_manifest": {
            "path": HISTORICAL_V61_MANIFEST.as_posix(),
            "verdict": v61_result.verdict,
            "reasons": v61_result.reasons,
        },
        "backlog": {
            "path": BACKLOG_PATH.as_posix(),
            "unresolved_checkbox_count": len(unresolved),
            "unresolved_preview": unresolved[:10],
        },
        "accepted_final_manifests": final_accepted,
        "stable_claim_leaks": phrase_leaks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate repository-wide V6.2 release truth claims.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args(argv)

    report = build_report(ROOT)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
