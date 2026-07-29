from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

PUBLIC_MODULES = [
    "localforge",
    "localforge.api.app",
    "localforge.cli.main",
    "localforge.core.config",
    "localforge.events.bus",
    "localforge.gitops.manager",
    "localforge.llm.factory",
    "localforge.models.domain",
    "localforge.pipeline.engine",
    "localforge.prd.compiler",
    "localforge.quality.gates",
    "localforge.safety.action_gateway",
    "localforge.services",
    "localforge.services.compliance_evidence",
    "localforge.services.task",
    "localforge.storage",
    "localforge.storage.bootstrap",
    "localforge.storage.database",
    "localforge.version",
]


def main() -> int:
    imported: list[str] = []
    failed: list[dict[str, str]] = []
    for module in PUBLIC_MODULES:
        try:
            importlib.import_module(module)
            imported.append(module)
        except Exception as exc:
            failed.append(
                {
                    "module": module,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    print(
        json.dumps(
            {
                "imported": imported,
                "failed": failed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
