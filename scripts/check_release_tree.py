from __future__ import annotations

import argparse
import json
from pathlib import Path

from localforge.services.release_audit import ReleaseTreeAuditor


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit tracked release files without cleanup.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--scope", default=".", help="Tracked path scope to audit.")
    parser.add_argument("--output", help="Optional JSON report output path.")
    args = parser.parse_args()

    auditor = ReleaseTreeAuditor(Path(args.root).resolve())
    report = auditor.audit(args.scope)
    payload = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
