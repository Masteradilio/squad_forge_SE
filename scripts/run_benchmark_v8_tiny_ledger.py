"""Run a real small PRD through the V8 LoopX-like control plane."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_benchmark_v7_mini_prd as base  # noqa: E402


base.WORKSPACE = ROOT / "benchmarks" / "workspaces" / "v8-tiny-ledger"
base.PRD = ROOT / "docs" / "PRD_V8_TINY_LEDGER.md"
base.EVIDENCE = ROOT / "docs" / "e2e" / "v8" / "tiny_ledger"
base.EXPECTED_TASKS = 4
base.BENCHMARK_LABEL = "ForgeOS V8 LoopX-like Tiny Ledger Real PRD Benchmark"
base.METRICS_FILENAME = "tiny_ledger_metrics.json"
base.REPORT_FILENAME = "tiny_ledger_report.md"
base.FIXTURE_SOURCES = [
    ROOT / "scripts" / "fixtures" / "v8_tiny_ledger_create_acceptance.py",
    ROOT / "scripts" / "fixtures" / "v8_tiny_ledger_settle_acceptance.py",
    ROOT / "scripts" / "fixtures" / "v8_tiny_ledger_summary_acceptance.py",
]


def _apply_contracts(database: Path) -> dict[str, int]:
    summary = {"chief_only": 0, "chief_led": 0, "local_assisted": 0}
    allowed_files = [
        "app/tiny_ledger.py",
        "tests/test_tiny_ledger.py",
        "docs/pr.md",
        "docs/cost_benchmark.md",
        "docs/review.md",
        "docs/risk.md",
    ]
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, title, description, metadata_json FROM tasks ORDER BY id"
        ).fetchall()
        for index, (task_id, title, description, metadata_raw) in enumerate(rows):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            seniority = (
                "chief_only"
                if index in (2, 3)
                else "local_assisted"
                if index == 0
                else "chief_led"
            )
            behaviors: list[str] = []
            if index == 0:
                behaviors = ["add_entry creates a pending entry and list_entries returns it"]
            elif index == 1:
                behaviors = ["blank labels fail and settle_entry changes only the selected entry"]
            elif index == 2:
                behaviors = ["summarize returns total, settled, and pending without mutating the store"]
            metadata["task_contract"] = {
                "allowed_files": allowed_files,
                "canonical_test_command": (
                    "git diff --check"
                    if index == 3
                    else "python -m pytest tests/test_tiny_ledger.py -q"
                ),
                "seniority_class": seniority,
                "visual_required": False,
                "acceptance_test_policy": "observable_behavior_only",
                "acceptance_behaviors": behaviors,
                "implementation_notes": [
                    "Use the exact public functions and behavior named by the PRD.",
                    "Acceptance must execute app/tiny_ledger.py, never a duplicate algorithm in the test.",
                ],
                "v8_loopx_like_benchmark": True,
                "source_title": str(title),
                "source_description": str(description),
            }
            if index < 3:
                metadata["task_contract"].update(
                    {
                        "acceptance_test_fixture_source": str(base.FIXTURE_SOURCES[index]),
                        "acceptance_test_fixture_target": "tests/test_tiny_ledger.py",
                    }
                )
            connection.execute(
                "UPDATE tasks SET risk_level = ?, metadata_json = ? WHERE id = ?",
                ("low" if seniority == "local_assisted" else "medium", json.dumps(metadata), task_id),
            )
            summary[seniority] += 1
        connection.commit()
    return summary


base._apply_contracts = _apply_contracts


async def main() -> int:
    """Run the benchmark and export only review-safe durable evidence."""
    code = await base.main()
    base.EVIDENCE.mkdir(parents=True, exist_ok=True)
    control_plane_dir = base.WORKSPACE / ".localforge" / "control_plane"
    state_files = sorted(control_plane_dir.glob("run-*.json"), key=lambda path: path.stat().st_mtime)
    event_files = sorted(
        control_plane_dir.glob("run-*.events.jsonl"), key=lambda path: path.stat().st_mtime
    )
    exported: dict[str, str | None] = {
        "control_plane": None,
        "events": None,
    }
    if state_files:
        target = base.EVIDENCE / "control_plane.json"
        target.write_text(state_files[-1].read_text(encoding="utf-8"), encoding="utf-8")
        exported["control_plane"] = target.name
    if event_files:
        target = base.EVIDENCE / "events.jsonl"
        target.write_text(event_files[-1].read_text(encoding="utf-8"), encoding="utf-8")
        exported["events"] = target.name
    metrics_path = base.EVIDENCE / base.METRICS_FILENAME
    status = "UNKNOWN"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            status = str(metrics.get("status", status))
        except json.JSONDecodeError:
            status = "INVALID_METRICS"
    manifest = {
        "schema_version": 1,
        "benchmark": base.BENCHMARK_LABEL,
        "status": status,
        "workspace": str(base.WORKSPACE.relative_to(ROOT)).replace("\\", "/"),
        "exported": exported,
        "report": base.REPORT_FILENAME,
        "metrics": base.METRICS_FILENAME,
        "exit_code": code,
    }
    (base.EVIDENCE / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    acceptance_report = base.EVIDENCE / "acceptance_report.md"
    report = base.EVIDENCE / base.REPORT_FILENAME
    if report.exists():
        acceptance_report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
