from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from localforge.services.compliance_evidence import EVIDENCE_READY, ComplianceEvidenceValidator  # noqa: E402
from localforge.services.file_hashes import stable_file_sha256  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate committed V6.2 candidate evidence manifests.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args(argv)

    evidence_root = ROOT / "docs" / "e2e" / "v6_2_compliance"
    manifest_paths = sorted(evidence_root.glob("phase_R*/candidate_manifest.json"))
    validator = ComplianceEvidenceValidator(ROOT)
    results: list[dict[str, object]] = []
    failed = False

    for manifest_path in manifest_paths:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = validator.validate_manifest(manifest_path)
        passed = result.verdict == EVIDENCE_READY
        failed = failed or not passed
        results.append(
            {
                "manifest": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_file_sha256": stable_file_sha256(manifest_path),
                "manifest_sha256": str(manifest_payload.get("manifest_sha256", "")),
                "verdict": result.verdict,
                "passed": passed,
                "reasons": result.reasons,
            }
        )

    payload = {
        "schema_version": "localforge.v6_2.candidate_evidence_check.v1",
        "manifest_count": len(manifest_paths),
        "passed": not failed and bool(manifest_paths),
        "results": results,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 1 if failed or not manifest_paths else 0


if __name__ == "__main__":
    raise SystemExit(main())
