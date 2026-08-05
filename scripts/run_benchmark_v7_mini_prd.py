"""Run a bounded real PRD benchmark through the ForgeOS CLI and scheduler."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "benchmarks" / "workspaces" / "v7-mini-checklist"
PRD = ROOT / "docs" / "PRD_MINI_CHECKLIST.md"
EVIDENCE = ROOT / "docs" / "e2e" / "v7"
EXPECTED_TASKS = 4  # three feature tasks plus the compiler's release assembly task
BENCHMARK_LABEL = "ForgeOS V7 Mini Checklist Real PRD Benchmark"
METRICS_FILENAME = "mini_prd_benchmark_metrics.json"
REPORT_FILENAME = "mini_prd_benchmark_report.md"

FIXTURE_SOURCES = [
    ROOT / "scripts" / "fixtures" / "v7_mini_checklist_create_acceptance.py",
    ROOT / "scripts" / "fixtures" / "v7_mini_checklist_persistence_acceptance.py",
    ROOT / "scripts" / "fixtures" / "v7_mini_checklist_export_acceptance.py",
]

sys.path.insert(0, str(ROOT))
from scripts import run_benchmark_v3_only as cloud  # noqa: E402


def _db_path() -> Path:
    return WORKSPACE / ".localforge" / "localforge.db"


def _apply_contracts(database: Path) -> dict[str, int]:
    summary = {"chief_only": 0, "chief_led": 0, "local_assisted": 0}
    allowed_files = [
        "app/mini_checklist.html",
        "tests/test_mini_checklist.py",
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
            # Keep one tiny bounded task local-assisted. The export and final
            # assembly tasks are high-authority Chief work; this makes the
            # benchmark exercise the real V7 routing contract instead of
            # treating release assembly as an ordinary local edit.
            if str(title).startswith("Integration & Release Assembly"):
                seniority = "chief_only"
            elif index == 0:
                seniority = "local_assisted"
            elif index == 2:
                seniority = "chief_only"
            else:
                seniority = "chief_led"
            risk = "low" if seniority == "local_assisted" else "medium"
            is_integration = str(title).startswith("Integration & Release Assembly")
            metadata["task_contract"] = {
                "allowed_files": allowed_files,
                "canonical_test_command": (
                    "git diff --check"
                    if is_integration
                    else "python -m pytest tests/test_mini_checklist.py -q"
                ),
                "seniority_class": seniority,
                "visual_required": False,
                "acceptance_test_policy": "observable_behavior_only",
                "acceptance_behaviors": (
                    [
                        "create and list a checklist item with id, title, completed, and created_at",
                    ]
                    if index == 0
                    else [
                        "reject an empty title and preserve completion state after restart",
                    ]
                    if index == 1
                    else [
                        "export total, completed, and pending counts as JSON",
                    ]
                    if index == 2
                    else []
                ),
                "implementation_notes": [
                    "Do not invent required function or DOM identifier names from the task title.",
                    "Acceptance tests must execute the real HTML/JavaScript behavior or use a browser/Node harness; source-string checks alone are invalid.",
                ],
                "v7_api_led_benchmark": True,
                "source_title": str(title),
                "source_description": str(description),
            }
            if index in (0, 1, 2):
                metadata["task_contract"].update(
                    {
                        "acceptance_test_fixture_source": str(FIXTURE_SOURCES[index]),
                        "acceptance_test_fixture_target": "tests/test_mini_checklist.py",
                    }
                )
            connection.execute(
                "UPDATE tasks SET risk_level = ?, metadata_json = ? WHERE id = ?",
                (risk, json.dumps(metadata), task_id),
            )
            summary[seniority] += 1
        connection.commit()
    return summary


def _patch_v7_config(workspace: Path, route: str, free_routes: list[str]) -> None:
    path = workspace / ".localforge" / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gateway = (
        os.environ.get("OMNIROUTE_URL")
        or cloud.root_env_values().get("OMNIROUTE_URL")
        or "http://127.0.0.1:20128/v1"
    )
    config["models"] = {
        **config.get("models", {}),
        "provider": "omniroute",
        "base_url": gateway,
        "default_model": route,
        "fallback_models": free_routes,
    }
    config["chief_engineer"] = {
        **config.get("chief_engineer", {}),
        "enabled": True,
        "provider": "omniroute",
        "base_url": gateway,
        "model": route,
        "visual_model": route,
        "fallback_models": free_routes,
        "visual_fallback_models": free_routes,
        "fallback_provider": None,
        "fallback_base_url": None,
        "fallback_model": None,
        "timeout": 120.0,
    }
    config["sandbox"] = {**config.get("sandbox", {}), "type": "local"}
    config["budgets"] = {
        **config.get("budgets", {}),
        # Free OmniRoute routes can require a bounded fallback ladder plus a
        # release-evidence repair. Keep the ceiling finite, but do not turn a
        # recoverable validation failure into an artificial budget blocker.
        "max_paid_calls": 24,
        "max_paid_input_tokens": 200_000,
        "max_paid_output_tokens": 60_000,
        "max_paid_usd": 0.50,
        "max_paid_usd_absolute": 0.75,
        "max_task_duration": 300.0,
        "max_run_time": 1200.0,
        "max_repair_attempts": 2,
        "max_run_recovery_cycles": 2,
        # A complete single-file HTML implementation plus its acceptance
        # harness is still a bounded change, but commonly exceeds 2 KiB.
        "max_diff_growth": 24_000,
    }
    path.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8", newline="\n")


def _query(database: Path) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        task_statuses = dict(
            connection.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
        )
        runs = dict(connection.execute("SELECT status, COUNT(*) FROM runs GROUP BY status").fetchall())
        task_runs = int(connection.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0])
        artifacts = int(connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
        calls = int(connection.execute("SELECT COUNT(*) FROM model_call_ledger").fetchone()[0])
        providers = dict(
            connection.execute(
                "SELECT provider, COUNT(*) FROM model_call_ledger GROUP BY provider"
            ).fetchall()
        )
        cost = float(
            connection.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM model_call_ledger"
            ).fetchone()[0]
            or 0
        )
        return {
            "task_statuses": {str(k): int(v) for k, v in task_statuses.items()},
            "runs": {str(k): int(v) for k, v in runs.items()},
            "task_runs_executed": task_runs,
            "artifacts_generated": artifacts,
            "model_calls_logged": calls,
            "calls_by_provider": {str(k): int(v) for k, v in providers.items()},
            "estimated_cost_usd": cost,
        }


def _control_plane_projection() -> dict[str, Any] | None:
    candidates = sorted((WORKSPACE / ".localforge" / "control_plane").glob("run-*.json"))
    if not candidates:
        return None
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


async def main() -> int:
    print(f"=== {BENCHMARK_LABEL} ===")
    if not PRD.is_file():
        raise FileNotFoundError(PRD)
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    await cloud.prune_git_worktrees()

    commands: list[dict[str, Any]] = []

    async def run(args: list[str]) -> int:
        code, stdout, stderr = await cloud.run_cli_command(str(WORKSPACE), args)
        commands.append({"args": args, "exit_code": code, "stderr_tail": stderr[-1200:]})
        if code != 0:
            print(f"[command failed] {' '.join(args)}\n{stderr[-1200:]}")
        return code

    init_code = await run(["init"])
    import_code = await run(["import-prd", str(PRD)])
    database = _db_path()
    if not database.is_file():
        raise RuntimeError(f"benchmark database was not created: {database}")
    contract_summary = _apply_contracts(database)
    with sqlite3.connect(database) as connection:
        imported_task_count = int(connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])

    gateway = (
        os.environ.get("OMNIROUTE_URL")
        or cloud.root_env_values().get("OMNIROUTE_URL")
        or "http://127.0.0.1:20128/v1"
    )
    gateway_ok, models, gateway_detail = await cloud.check_omniroute_status(gateway)
    routes = cloud._explicit_free_routes(models)
    # The catalog order is not a quality signal: OmniRoute often advertises a
    # generic free pool before coding-specialized routes. Prefer routes with a
    # public coding focus, then fall back through every live free route. The
    # probe still decides whether a candidate is actually reachable.
    preferred_free_routes = [
        "oc/deepseek-v4-flash-free",
        "oc/north-mini-code-free",
        "openrouter/cohere/north-mini-code:free",
        "openrouter/openai/gpt-oss-20b:free",
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/inclusionai/ling-3.0-flash:free",
    ]
    routes = list(
        dict.fromkeys(
            [route for route in preferred_free_routes if route in routes] + routes
        )
    )
    probe_ok: bool = False
    selected_route: str | None = None
    probe_failures: list[str] = []
    if gateway_ok and routes:
        probe_ok, selected_route, probe_failures = await cloud.probe_omniroute_completion(
            gateway, routes
        )
    route = selected_route or (routes[0] if routes else "auto/best-free")
    route_ladder = ",".join(dict.fromkeys([route, *routes]))
    # The CLI subprocess also loads the repository .env.  Set the benchmark's
    # discovered ladder explicitly so a stale root fallback cannot silently
    # replace the live OmniRoute free catalog during Chief recovery.
    os.environ.update(
        {
            "OMNIROUTE_URL": gateway,
            "LOCALFORGE_MODEL_PROVIDER": "omniroute",
            "LOCALFORGE_MODEL_BASE_URL": gateway,
            "LOCALFORGE_DEFAULT_MODEL": route,
            "LOCALFORGE_FALLBACK_MODELS": route_ladder,
            "LOCALFORGE_CHIEF_PROVIDER": "omniroute",
            "LOCALFORGE_CHIEF_BASE_URL": gateway,
            "LOCALFORGE_CHIEF_MODEL": route,
            "LOCALFORGE_CHIEF_VISUAL_MODEL": route,
            "LOCALFORGE_CHIEF_FALLBACK_MODELS": route_ladder,
            "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS": route_ladder,
            "LOCALFORGE_CHIEF_MAX_DIFF_GROWTH": "24000",
        }
    )
    _patch_v7_config(WORKSPACE, route, list(dict.fromkeys([route, *routes])))

    gateway_ready_for_run = gateway_ok and bool(routes) and probe_ok
    if not gateway_ready_for_run:
        gateway_blocker = (
            "OmniRoute structured free-route preflight failed; refusing to start "
            f"the unattended run. {probe_failures}"
        )
        print(f"[Blocker] {gateway_blocker}")
        plan_code = await run(["plan", "--approve-all"])
        run_code = 125
        commands.append(
            {
                "args": ["run", "--unattended"],
                "exit_code": run_code,
                "stderr_tail": f"Skipped by preflight: {gateway_blocker}",
            }
        )
    else:
        plan_code = await run(["plan", "--approve-all"])
        run_code = await run(["run", "--unattended"])
    summary = _query(database)
    projection = _control_plane_projection()
    task_statuses = summary["task_statuses"]
    all_ready = task_statuses.get("PR_READY", 0) == EXPECTED_TASKS
    control_plane_complete = bool(
        projection
        and projection.get("goal", {}).get("status") == "COMPLETED"
        and all(todo.get("status") == "PASSED" for todo in projection.get("todos", []))
    )
    gateway_usable = gateway_ready_for_run
    acceptance_conditions = (
        init_code == import_code == plan_code == run_code == 0
        and imported_task_count == EXPECTED_TASKS
        and gateway_usable
        and all_ready
        and control_plane_complete
    )
    # A missing structured route is an external precondition failure, not a
    # partial product result. Keep PARTIAL for runs that actually started and
    # then failed a task; keep BLOCKED for preflight failures.
    status = "ACCEPTED" if acceptance_conditions else (
        "BLOCKED" if not gateway_usable else "PARTIAL"
    )
    blockers: list[str] = []
    if not gateway_usable:
        blockers.append(f"OmniRoute preflight: {gateway_detail}; {probe_failures}")
    elif not probe_ok:
        gateway_detail += "; direct route probe was advisory-only; the run exercised OmniRoute successfully"
    run_started = run_code == 0
    if run_started and imported_task_count != EXPECTED_TASKS:
        blockers.append(
            f"PRD task count: imported {imported_task_count}, expected {EXPECTED_TASKS}"
        )
    if run_started and not all_ready:
        blockers.append(f"SQLite task statuses: {task_statuses}")
    if run_started and not control_plane_complete:
        blockers.append("Control-plane goal did not reach COMPLETED with all todos PASSED")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    metrics = {
        "benchmark_name": BENCHMARK_LABEL,
        "generated_at": datetime.now(UTC).isoformat(),
        "prd_file": str(PRD.relative_to(ROOT)).replace("\\", "/"),
        "workspace": str(WORKSPACE.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "blockers": blockers,
        "gateway": {
            "base_url": gateway,
            "catalog_reachable": gateway_ok,
            "structured_probe_passed": probe_ok,
            "structured_probe_advisory": gateway_usable and not probe_ok,
            "detail": gateway_detail,
            "selected_route": selected_route,
            "free_routes_seen": routes,
        },
        "routing_contract_summary": contract_summary,
        "imported_task_count": imported_task_count,
        "sqlite": summary,
        "control_plane": {
            "present": projection is not None,
            "completed": control_plane_complete,
            "revision": projection.get("revision") if projection else None,
            "receipts": len(projection.get("receipts", [])) if projection else 0,
            "events": len(projection.get("events", [])) if projection else 0,
        },
        "commands": commands,
        "limitations": [
            "Acceptance means automated PR evidence and durable control-plane completion; human review remains required.",
            "The benchmark uses a deliberately small PRD and does not predict HP12C success.",
        ],
    }
    (EVIDENCE / METRICS_FILENAME).write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE / REPORT_FILENAME).write_text(
        f"# {BENCHMARK_LABEL}\n\n"
        f"- Status: **{status}**\n"
        f"- Tasks: **{task_statuses.get('PR_READY', 0)}/{EXPECTED_TASKS} PR_READY**\n"
        f"- Task runs: **{summary['task_runs_executed']}**\n"
        f"- Model calls: **{summary['model_calls_logged']}**\n"
        f"- Cost: **${summary['estimated_cost_usd']:.6f}**\n"
        f"- Control plane completed: **{control_plane_complete}**\n\n"
        "## Blockers\n\n"
        + ("\n".join(f"- {item}" for item in blockers) if blockers else "- None")
        + "\n\nThis report is generated from the workspace SQLite database and the "
        "durable control-plane projection. It is not human product acceptance.\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))
    return 0 if status == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
