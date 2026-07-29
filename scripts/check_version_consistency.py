from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from localforge.version import RELEASE_TAG, VERSION  # noqa: E402


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend_package = json.loads(
        (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    frontend_lock = json.loads(
        (ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )

    observed = {
        "backend": VERSION,
        "pyproject": pyproject["project"]["version"],
        "frontend_package": frontend_package["version"],
        "frontend_lock": frontend_lock["version"],
        "frontend_lock_root": frontend_lock["packages"][""]["version"],
    }
    mismatches = {
        name: value for name, value in observed.items() if value != VERSION
    }
    payload = {
        "version": VERSION,
        "release_tag": RELEASE_TAG,
        "observed": observed,
        "mismatches": mismatches,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
