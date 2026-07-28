"""Collect a portable V5 benchmark manifest without executing a model lane.

Each benchmark lane is run by the operator under its declared conditions. This
tool records the immutable inputs and the lane metrics afterwards, so published
claims can be reproduced without embedding a product-specific workflow in the
LocalForge runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LANES = ("frontier-api", "economy-api", "local-only", "hybrid")
REQUIRED_METRICS = (
    "acceptance_passed",
    "elapsed_seconds",
    "retries",
    "human_interventions",
    "model_calls",
    "paid_cost_usd",
    "local_inference_seconds",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_metadata(workspace: Path) -> dict[str, str | bool | None]:
    def read_git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(workspace), *args],
            capture_output=True,
            check=False,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    status = read_git("status", "--porcelain")
    return {
        "commit": read_git("rev-parse", "HEAD"),
        "dirty": bool(status) if status is not None else None,
    }


def load_metrics(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Metrics file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Metrics file must contain a JSON object")
    missing = [key for key in REQUIRED_METRICS if key not in payload]
    if missing:
        raise ValueError(
            f"Metrics file is missing required fields: {', '.join(missing)}"
        )
    return payload


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--lane", required=True, choices=LANES)
    cli.add_argument("--workspace", required=True, type=Path)
    cli.add_argument("--prd", required=True, type=Path)
    cli.add_argument("--metrics", required=True, type=Path)
    cli.add_argument("--acceptance-command", required=True)
    cli.add_argument("--output", required=True, type=Path)
    return cli


def collect(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    prd = args.prd.resolve()
    metrics_path = args.metrics.resolve()
    if not workspace.is_dir():
        raise ValueError(f"Workspace does not exist: {workspace}")
    for path in (prd, metrics_path):
        if not path.is_file():
            raise ValueError(f"Required file does not exist: {path}")

    node = shutil.which("node")
    node_version = None
    if node:
        result = subprocess.run(
            [node, "--version"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            node_version = result.stdout.strip()

    return {
        "format_version": 1,
        "evidence_status": "COLLECTED_NOT_EVALUATED",
        "lane": args.lane,
        "collected_at": datetime.now(UTC).isoformat(),
        "workspace": {"name": workspace.name, "git": git_metadata(workspace)},
        "inputs": {
            "prd": {"name": prd.name, "sha256": sha256_file(prd)},
            "metrics": {
                "name": metrics_path.name,
                "sha256": sha256_file(metrics_path),
            },
        },
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "node": node_version,
        },
        "acceptance": {"command": args.acceptance_command},
        "metrics": load_metrics(metrics_path),
        "limitations": [
            "This manifest records one lane only.",
            "A comparative claim requires all four V5 lanes with identical inputs "
            "and independent review.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        manifest = collect(args)
    except ValueError as exc:
        parser().error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
