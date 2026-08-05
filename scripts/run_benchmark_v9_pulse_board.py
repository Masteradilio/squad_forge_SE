"""Run a real small PulseBoard PRD through the V9 LoopX-like path."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_benchmark_v7_mini_prd as base  # noqa: E402


RUN_SUFFIX = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
base.WORKSPACE = ROOT / "benchmarks" / "workspaces" / f"v9-pulse-board-{RUN_SUFFIX}"
base.PRD = ROOT / "docs" / "PRD_V9_PULSE_BOARD.md"
base.EVIDENCE = ROOT / "docs" / "e2e" / "v9" / "pulse_board"
base.EXPECTED_TASKS = 4
base.BENCHMARK_LABEL = "ForgeOS V9 LoopX-like PulseBoard Real PRD Benchmark"
base.METRICS_FILENAME = "pulse_board_metrics.json"
base.REPORT_FILENAME = "pulse_board_report.md"
base.FIXTURE_SOURCES = [
    ROOT / "scripts" / "fixtures" / "v9_pulse_board_create_acceptance.py",
    ROOT / "scripts" / "fixtures" / "v9_pulse_board_validation_acceptance.py",
    ROOT / "scripts" / "fixtures" / "v9_pulse_board_summary_acceptance.py",
]


def _apply_contracts(database: Path) -> dict[str, int]:
    summary = {"chief_only": 0, "chief_led": 0, "local_assisted": 0}
    allowed_files = [
        "app/pulse_board.py",
        "tests/test_pulse_board_create.py",
        "tests/test_pulse_board_validation.py",
        "tests/test_pulse_board_summary.py",
        "docs/pr.md",
        "docs/cost_benchmark.md",
        "docs/review.md",
        "docs/risk.md",
        "docs/release_manifest.md",
    ]
    local_allowed_files = [
        "app/pulse_board.py",
        "tests/test_pulse_board_create.py",
    ]
    behaviors = [
        ["add_pulse creates a persistent record and list_pulses preserves creation order"],
        ["blank titles fail and complete_pulse changes only the selected record"],
        ["summarize returns total, completed, and pending without mutating the store"],
        [
            "release_manifest records the production module and canonical test command",
        ],
    ]
    test_targets = [
        "tests/test_pulse_board_create.py",
        "tests/test_pulse_board_validation.py",
        "tests/test_pulse_board_summary.py",
    ]
    release_allowed_files = [
        "app/pulse_board.py",
        "docs/pr.md",
        "docs/cost_benchmark.md",
        "docs/review.md",
        "docs/risk.md",
        "docs/release_manifest.md",
    ]
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, title, description, metadata_json FROM tasks ORDER BY id"
        ).fetchall()
        task_ids = [int(row[0]) for row in rows]
        for index, (task_id, title, description, metadata_raw) in enumerate(rows):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            seniority = "local_assisted" if index == 0 else "chief_only" if index in (2, 3) else "chief_led"
            is_release = index == 3
            if is_release:
                title = "Release assembly: publish PulseBoard evidence manifest"
                description = (
                    "Preserve all accumulated PulseBoard capabilities, run the complete "
                    "acceptance suite, and create docs/release_manifest.md recording "
                    "the production module and canonical test command."
                )
                acceptance_criteria = json.dumps(
                    [
                        "All accumulated PulseBoard acceptance tests remain executable and pass",
                        "docs/release_manifest.md exists and names app/pulse_board.py",
                        "docs/release_manifest.md names tests/ and the full acceptance command",
                        "python -m pytest tests -q passes for the release worktree",
                    ]
                )
                connection.execute(
                    "UPDATE tasks SET title = ?, description = ?, acceptance_criteria = ? WHERE id = ?",
                    (title, description, acceptance_criteria, task_id),
                )
            metadata["task_contract"] = {
                "allowed_files": (
                    release_allowed_files
                    if is_release
                    else local_allowed_files
                    if index == 0
                    else allowed_files
                ),
                "canonical_test_command": (
                    "python -m pytest tests -q"
                    if is_release
                    else f"python -m pytest {test_targets[index]} -q"
                ),
                "seniority_class": seniority,
                "visual_required": False,
                "acceptance_test_policy": "observable_behavior_only",
                "acceptance_behaviors": (
                    behaviors[0] + behaviors[1] + behaviors[2] + behaviors[3]
                    if is_release
                    else behaviors[index]
                ),
                "acceptance_test_fixture_source": str(base.FIXTURE_SOURCES[index]) if index < 3 else None,
                "acceptance_test_fixture_target": test_targets[index] if index < 3 else None,
                "required_product_files": ["app/pulse_board.py"],
                "required_artifact": (
                    {
                        "path": "docs/release_manifest.md",
                        "markers": [
                            "app/pulse_board.py",
                            "tests/",
                            "python -m pytest tests -q",
                        ],
                    }
                    if is_release
                    else None
                ),
                "implementation_notes": [
                    "Use the exact public functions named in the PRD.",
                    "This is a Python product: create and execute app/pulse_board.py; do not infer an HTML entrypoint.",
                    "Acceptance must execute app/pulse_board.py, never a duplicate algorithm in the test.",
                    "The public API is exactly add_pulse(store, title), list_pulses(store), complete_pulse(store, pulse_id), and summarize(store).",
                    "add_pulse must persist a positive integer id starting at 1, a non-empty ISO-8601 created_at string, the supplied title, and completed=False.",
                    "complete_pulse must raise KeyError for every unknown id, including non-numeric values such as 'missing'; do not leak ValueError from int conversion.",
                    "Preserve all accumulated behaviors and the JSON file format; do not replace the module with an unrelated class, metrics API, or test-only implementation.",
                    "For the release task, create docs/release_manifest.md with the required markers; do not rewrite a product module that already passes the accumulated suite unless validation proves it is broken.",
                ],
                "v9_loopx_like_benchmark": True,
                "source_title": str(title),
                "source_description": str(description),
            }
            connection.execute(
                "UPDATE tasks SET dependency_task_ids = ?, risk_level = ?, metadata_json = ? WHERE id = ?",
                (
                    json.dumps([] if index == 0 else [task_ids[index - 1]]),
                    "low" if seniority == "local_assisted" else "medium",
                    json.dumps(metadata),
                    task_id,
                ),
            )
            summary[seniority] += 1
        connection.commit()
    return summary


base._apply_contracts = _apply_contracts


def _run_final_acceptance() -> dict[str, object]:
    """Validate accumulated release output independently of task statuses."""
    worktree = base.WORKSPACE / ".localforge" / "worktrees" / "lf-prd-004"
    fixture_paths = [
        ROOT / "scripts" / "fixtures" / "v9_pulse_board_create_acceptance.py",
        ROOT / "scripts" / "fixtures" / "v9_pulse_board_validation_acceptance.py",
        ROOT / "scripts" / "fixtures" / "v9_pulse_board_summary_acceptance.py",
    ]
    if not worktree.is_dir():
        return {"passed": False, "reason": "release worktree is missing", "commands": []}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(worktree)
    commands: list[dict[str, object]] = []
    for command in (
        [sys.executable, "-m", "pytest", "tests", "-q"],
        [sys.executable, "-m", "pytest", *[str(path) for path in fixture_paths], "-q"],
    ):
        completed = subprocess.run(
            command,
            cwd=worktree,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        commands.append(
            {
                "command": command[2:],
                "exit_code": completed.returncode,
                "stdout_tail": (completed.stdout or "")[-1200:],
                "stderr_tail": (completed.stderr or "")[-1200:],
            }
        )
    manifest_path = worktree / "docs" / "release_manifest.md"
    manifest_text = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else ""
    manifest_ok = all(
        marker in manifest_text
        for marker in ("app/pulse_board.py", "tests/", "python -m pytest tests -q")
    )
    return {
        "passed": all(item["exit_code"] == 0 for item in commands) and manifest_ok,
        "manifest_ok": manifest_ok,
        "commands": commands,
    }


async def main() -> int:
    base._apply_contracts = _apply_contracts
    code = await base.main()
    base.EVIDENCE.mkdir(parents=True, exist_ok=True)
    control_plane_dir = base.WORKSPACE / ".localforge" / "control_plane"
    state_files = sorted(control_plane_dir.glob("run-*.json"), key=lambda path: path.stat().st_mtime)
    event_files = sorted(
        control_plane_dir.glob("run-*.events.jsonl"), key=lambda path: path.stat().st_mtime
    )
    exported: dict[str, str | None] = {"control_plane": None, "events": None}
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
    metrics: dict[str, object] = {}
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            status = str(metrics.get("status", status))
        except json.JSONDecodeError:
            status = "INVALID_METRICS"
    final_validation = _run_final_acceptance()
    metrics["final_validation"] = final_validation
    if not final_validation.get("passed"):
        if status == "ACCEPTED":
            status = "PARTIAL"
        blockers = metrics.setdefault("blockers", [])
        if isinstance(blockers, list):
            blockers.append("Independent final release acceptance failed")
    metrics["status"] = status
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    report = base.EVIDENCE / base.REPORT_FILENAME
    if report.exists():
        report_text = report.read_text(encoding="utf-8")
        report_text = report_text.replace("- Status: **ACCEPTED**", f"- Status: **{status}**")
        report_text += "\n## Independent final release acceptance\n\n"
        report_text += f"- Passed: **{bool(final_validation.get('passed'))}**\n"
        report.write_text(report_text, encoding="utf-8")
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
    if report.exists():
        (base.EVIDENCE / "acceptance_report.md").write_text(
            report.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return 0 if status == "ACCEPTED" and final_validation.get("passed") else max(code, 2)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
