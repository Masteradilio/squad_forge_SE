"""Run the real HP12C acceptance flow through the OmniRoute gateway only.

This runner deliberately fails closed. A reachable /v1/models endpoint is not
enough: at least one catalog-advertised free route must complete a structured
probe before the scheduler is allowed to spend time on the PRD.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS = ROOT / "samples" / "e2e-hp12c-platinum" / "docs"
DEFAULT_WORKSPACE = ROOT / "benchmarks" / "workspaces" / "hp12c-cloud-acceptance-live"


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    root_env = dotenv_values(ROOT / ".env")
    configured = root_env.get(name)
    return configured if isinstance(configured, str) and configured else None


def _free_route(model: str) -> bool:
    model = model.strip().lower()
    return model.endswith(":free") or "-free" in model or "free/" in model


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    api_key = _env_value("OMNIROUTE_API_KEY")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        try:
            return response.status, json.loads(body)
        except json.JSONDecodeError:
            return response.status, body[:500]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return exc.code, detail
    except Exception as exc:
        return 0, str(exc)


def _omniroute_preflight(base_url: str) -> tuple[bool, list[str], dict[str, Any]]:
    timeout = max(5.0, min(30.0, float(_env_value("LOCALFORGE_CLOUD_PREFLIGHT_ROUTE_TIMEOUT") or 15)))
    catalog_status, catalog_body = _request_json(
        f"{base_url.rstrip('/')}/models", timeout=timeout
    )
    if catalog_status != 200 or not isinstance(catalog_body, dict):
        return False, [], {
            "catalog": f"HTTP {catalog_status}: {catalog_body}",
            "completion": "not attempted",
        }
    routes = [
        str(item["id"])
        for item in catalog_body.get("data", [])
        if isinstance(item, dict) and item.get("id") and _free_route(str(item["id"]))
    ]
    if not routes:
        return False, [], {
            "catalog": "reachable but no explicit free route was advertised",
            "completion": "not attempted",
        }

    failures: list[str] = []
    probe = {
        "model": routes[0],
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with one action: "
                    '{"actions":[{"kind":"write_file","path":"probe.txt",'
                    '"content":"ok"}]}'
                ),
            },
            {"role": "user", "content": "Return the structured probe now."},
        ],
        "stream": False,
        "max_tokens": 128,
        "temperature": 0,
        "reasoning_effort": "none",
    }
    for route in routes[:8]:
        probe["model"] = route
        status, body = _request_json(
            f"{base_url.rstrip('/')}/chat/completions",
            payload=probe,
            timeout=timeout,
        )
        content = ""
        if isinstance(body, dict):
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            parsed = json.loads(content.strip()) if isinstance(content, str) else None
        except json.JSONDecodeError:
            parsed = None
        if status == 200 and isinstance(parsed, dict) and parsed.get("actions"):
            return True, routes, {
                "catalog": f"{len(routes)} free route(s) advertised",
                "completion": f"structured probe passed via {route}",
                "verified_route": route,
            }
        failures.append(f"{route}: HTTP {status}: {body}")
    return False, routes, {
        "catalog": f"{len(routes)} free route(s) advertised",
        "completion": "no free route completed the structured probe",
        "failures": failures,
    }


def _run_command(
    workspace: Path, python: str, args: list[str], timeout: float
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    try:
        result = subprocess.run(
            [python, *args],
            cwd=workspace,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return 124, f"Command timed out after {timeout:.0f}s.\n{output}"


def _initialize_workspace(workspace: Path, python: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    docs = workspace / "docs"
    docs.mkdir(exist_ok=True)
    for name in ("PRD.md", "hp12c_platinum_design_target.png"):
        source = SAMPLE_DOCS / name
        if not source.is_file():
            raise RuntimeError(f"Missing benchmark input: {source}")
        target = docs / name
        if not target.exists():
            shutil.copy2(source, target)

    if not (workspace / ".git").exists():
        result = subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git init failed")
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        subprocess.run(["git", "config", "user.name", "ForgeOS Benchmark"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.email", "benchmark@forgeos.invalid"], cwd=workspace, check=True)
        subprocess.run(["git", "add", "--", "docs/PRD.md", "docs/hp12c_platinum_design_target.png"], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-m", "chore: initialize HP12C OmniRoute benchmark"], cwd=workspace, check=True)


def _query_summary(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    try:
        def grouped(table: str, column: str = "status") -> dict[str, int]:
            rows = connection.execute(
                f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}"
            ).fetchall()
            return {str(key): int(count) for key, count in rows}

        tasks = grouped("tasks")
        runs = grouped("runs")
        task_runs = grouped("task_runs")
        artifacts = int(connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
        calls = connection.execute(
            "SELECT provider, COUNT(*) FROM model_call_ledger GROUP BY provider"
        ).fetchall()
        calls_by_provider = {str(provider): int(count) for provider, count in calls}
        return {
            "tasks": tasks,
            "runs": runs,
            "task_runs": task_runs,
            "artifacts": artifacts,
            "calls_by_provider": calls_by_provider,
        }
    finally:
        connection.close()


def _write_report(workspace: Path, status: str, evidence: dict[str, Any]) -> Path:
    report_dir = workspace / ".localforge" / "artifacts" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "hp12c_cloud_acceptance.md"
    report.write_text(
        "# HP12C ForgeOS Cloud Acceptance\n\n"
        f"- Generated: `{datetime.now(UTC).isoformat()}`\n"
        f"- Status: **{status}**\n"
        "- Provider contract: **OmniRoute-only**\n\n"
        "## Evidence\n\n"
        "```json\n"
        + json.dumps(evidence, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--sandbox-type", choices=("docker", "local"), default="docker")
    parser.add_argument("--run-timeout", type=float, default=14400.0)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    base_url = _env_value("OMNIROUTE_URL") or "http://127.0.0.1:20128/v1"
    os.environ.update(
        {
            "OMNIROUTE_URL": base_url,
            "LOCALFORGE_MODEL_PROVIDER": "omniroute",
            "LOCALFORGE_MODEL_BASE_URL": base_url,
            "LOCALFORGE_DEFAULT_MODEL": "auto/best-free",
            "LOCALFORGE_CHIEF_PROVIDER": "omniroute",
            "LOCALFORGE_CHIEF_BASE_URL": base_url,
            "LOCALFORGE_CHIEF_MODEL": "auto/best-free",
            "LOCALFORGE_SANDBOX_TYPE": args.sandbox_type,
            "LOCALFORGE_OMNIROUTE_REASONING_EFFORT": "none",
        }
    )

    ready, routes, preflight = _omniroute_preflight(base_url)
    evidence: dict[str, Any] = {"preflight": preflight, "gateway_url": base_url}
    if not ready:
        report = _write_report(workspace, "BLOCKED", evidence)
        print(f"BLOCKED: OmniRoute completion pre-flight failed. Report: {report}")
        return 2

    ladder = ",".join(routes[:8])
    os.environ.update(
        {
            "LOCALFORGE_FALLBACK_MODELS": ladder,
            "LOCALFORGE_CHIEF_FALLBACK_MODELS": ladder,
            "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS": ladder,
        }
    )
    try:
        _initialize_workspace(workspace, args.python)
        commands = [
            (["-m", "localforge.cli.main", "init"], 180.0),
            (["-m", "localforge.cli.main", "import-prd", "docs/PRD.md"], 300.0),
            (["-m", "localforge.cli.main", "plan", "--approve-all"], 300.0),
            (["-m", "localforge.cli.main", "run", "--unattended"], args.run_timeout),
        ]
        outputs: list[dict[str, Any]] = []
        for command, timeout in commands:
            code, output = _run_command(workspace, args.python, command, timeout)
            outputs.append({"command": command, "exit_code": code, "tail": output[-4000:]})
            if code:
                evidence["commands"] = outputs
                report = _write_report(workspace, "BLOCKED", evidence)
                print(f"BLOCKED: command failed. Report: {report}")
                return 3

        database = workspace / ".localforge" / "localforge.db"
        summary = _query_summary(database)
        evidence.update({"commands": outputs, "sqlite": summary})
        task_count = sum(summary["tasks"].values())
        pr_ready = summary["tasks"].get("PR_READY", 0)
        non_omniroute = sum(
            count
            for provider, count in summary["calls_by_provider"].items()
            if provider.lower() != "omniroute"
        )
        status = (
            "ACCEPTED"
            if task_count > 0
            and pr_ready == task_count
            and summary["runs"].get("COMPLETED", 0) > 0
            and summary["calls_by_provider"].get("omniroute", 0) > 0
            and non_omniroute == 0
            else "PARTIAL"
        )
        report = _write_report(workspace, status, evidence)
        print(json.dumps({"status": status, "sqlite": summary, "report": str(report)}, indent=2))
        return 0 if status == "ACCEPTED" else 1
    except Exception as exc:
        evidence["exception"] = repr(exc)
        report = _write_report(workspace, "BLOCKED", evidence)
        print(f"BLOCKED: {exc}. Report: {report}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
