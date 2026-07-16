import asyncio
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

import yaml
from dotenv import dotenv_values

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_markdown_clean(path: str, content: str) -> None:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "\n".join(line.rstrip() for line in normalized.split("\n"))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(cleaned)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_source_state() -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()

    try:
        return {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--short")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def root_env_values() -> dict[str, str]:
    env_path = os.path.join(ROOT_DIR, ".env")
    if not os.path.exists(env_path):
        return {}
    return {
        key: value
        for key, value in dotenv_values(env_path).items()
        if isinstance(value, str) and value
    }

async def check_docker_status() -> tuple[bool, str]:
    """Return the real Docker daemon status without altering local state."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = (stdout if proc.returncode == 0 else stderr).decode(
            "utf-8", errors="replace"
        ).strip()
        return proc.returncode == 0, output
    except (FileNotFoundError, OSError) as exc:
        return False, str(exc)

async def check_ollama_status() -> tuple[bool, list[str]]:
    """Query the configured local Ollama daemon instead of fabricating models."""
    import urllib.error
    import urllib.request

    def fetch_models() -> list[str]:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            model["name"]
            for model in payload.get("models", [])
            if isinstance(model, dict) and isinstance(model.get("name"), str)
        ]

    try:
        models = await asyncio.to_thread(fetch_models)
        return True, models
    except (OSError, ValueError, urllib.error.URLError):
        return False, []

async def run_cli_command(cwd: str, args: list[str]) -> tuple[int, str, str]:
    """Executes a LocalForge CLI command in the specified directory using the absolute python venv path."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(ROOT_DIR, "backend")
    for key in (
        "NVIDIA_LLM_MODEL",
        "NVIDIA_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_API_KEY",
        "LOCALFORGE_MODEL_API_KEY",
    ):
        value = root_env_values().get(key)
        if value and not env.get(key):
            env[key] = value
    python_exe = sys.executable
    cmd_args = [python_exe, "-m", "localforge.cli.main"] + args

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )
    except Exception as e:
        return -1, "", str(e)

async def prune_git_worktrees():
    """Prunes missing/dangling git worktrees from the repository."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "prune",
            cwd=ROOT_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        print("Git worktrees pruned successfully.")
    except Exception as e:
        print(f"Failed to prune git worktrees: {e}")

async def patch_workspace_config(
    workspace_dir: str,
    default_model: str,
    docker_active: bool,
    chief_config: dict[str, Any],
):
    """Updates config.yaml for V4 API-led/economy-first routing."""
    config_path = os.path.join(workspace_dir, ".localforge", "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            
            if "models" not in cfg:
                cfg["models"] = {}
            cfg["models"]["provider"] = "ollama"
            cfg["models"]["base_url"] = "http://localhost:11434/v1"
            cfg["models"]["default_model"] = default_model
            cfg["models"]["fallback_models"] = [
                "gemma4:12b",
                "granite4.1:8b",
                "nemotron-3-nano:4b",
            ]
            
            if "sandbox" not in cfg:
                cfg["sandbox"] = {}
            if not docker_active:
                cfg["sandbox"]["type"] = "local"
            else:
                cfg["sandbox"]["type"] = "docker"

            if "chief_engineer" not in cfg:
                cfg["chief_engineer"] = {}
            cfg["chief_engineer"]["enabled"] = bool(chief_config.get("model"))
            cfg["chief_engineer"]["provider"] = chief_config.get("provider", "openrouter")
            cfg["chief_engineer"]["base_url"] = chief_config.get(
                "base_url", "https://openrouter.ai/api/v1"
            )
            cfg["chief_engineer"]["model"] = chief_config.get("model")
            cfg["chief_engineer"]["fallback_provider"] = chief_config.get("fallback_provider")
            cfg["chief_engineer"]["fallback_base_url"] = chief_config.get("fallback_base_url")
            cfg["chief_engineer"]["fallback_model"] = chief_config.get("fallback_model")
            cfg["chief_engineer"]["fallback_after_seconds"] = 30.0
            cfg["chief_engineer"]["timeout"] = 240.0

            if "budgets" not in cfg:
                cfg["budgets"] = {}
            cfg["budgets"]["max_paid_calls"] = 20
            cfg["budgets"]["max_paid_usd"] = 2.0
            cfg["budgets"]["max_task_duration"] = 1200.0
            cfg["budgets"]["max_run_time"] = 3600.0
            cfg["budgets"]["max_diff_growth"] = 5000
                
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False)
            print(
                f"Patched config at {config_path}: default_model={default_model}, "
                f"chief_model_configured={bool(chief_config.get('model'))}, "
                f"chief_provider={cfg['chief_engineer']['provider']}, "
                f"sandbox_type={cfg['sandbox']['type']}"
            )
        except Exception as e:
            print(f"Failed to patch config at {config_path}: {e}")


def chief_engineer_config_from_env() -> dict[str, Any]:
    env = os.environ.copy()
    env.update({k: v for k, v in root_env_values().items() if k not in env})
    if env.get("NVIDIA_LLM_MODEL") and env.get("NVIDIA_API_KEY"):
        return {
            "provider": "nvidia",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "model": env["NVIDIA_LLM_MODEL"],
            "api_key_configured": True,
            "fallback_provider": "openrouter" if env.get("OPENROUTER_API_KEY") else None,
            "fallback_base_url": "https://openrouter.ai/api/v1"
            if env.get("OPENROUTER_API_KEY")
            else None,
            "fallback_model": env.get("OPENROUTER_MODEL"),
            "fallback_api_key_configured": bool(env.get("OPENROUTER_API_KEY")),
        }
    return {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": env.get("OPENROUTER_MODEL"),
        "api_key_configured": bool(env.get("OPENROUTER_API_KEY")),
        "fallback_provider": None,
        "fallback_model": None,
        "fallback_api_key_configured": False,
    }


def classify_benchmark_status(
    *,
    preflight_failed: bool,
    task_statuses: dict[str, int],
    expected_tasks: int,
    runs_count: int,
    paid_chief_calls: int,
    local_model_calls: int,
    pr_artifacts_logged: int,
    run_exit_code: int,
    routing_contract_summary: dict[str, int],
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    imported_tasks = sum(task_statuses.values())
    pr_ready_tasks = task_statuses.get("PR_READY", 0)
    blocked_human_count = task_statuses.get(
        "BLOCKED_NEEDS_HUMAN_REVIEW", 0
    )

    if preflight_failed:
        return "BLOCKED", blockers
    if runs_count <= 0:
        return "REJECTED", ["No LocalForge run was recorded in SQLite."]
    if run_exit_code != 0:
        blockers.append(f"LocalForge CLI exited with code {run_exit_code}.")
    if imported_tasks != expected_tasks:
        blockers.append(
            f"Imported {imported_tasks} tasks, expected {expected_tasks}."
        )
    if blocked_human_count > 0:
        blockers.append(
            f"{blocked_human_count} task(s) are in BLOCKED_NEEDS_HUMAN_REVIEW "
            f"after the recovery budget was exhausted."
        )
    if pr_ready_tasks != expected_tasks:
        blockers.append(
            f"{expected_tasks - pr_ready_tasks} task(s) are not PR_READY: "
            f"{task_statuses}."
        )
    if paid_chief_calls <= 0:
        blockers.append(
            "V4 API-led routing did not execute any paid Chief Engineer call "
            "(NVIDIA primary or OpenRouter fallback)."
        )
    if local_model_calls <= 0:
        blockers.append(
            "V4 economy routing did not execute any local-model call."
        )
    if pr_artifacts_logged <= 0:
        blockers.append(
            "No PRArtifact was recorded for the benchmark run."
        )
    if not routing_contract_summary:
        blockers.append(
            "No task routing contracts were persisted for the V4 run."
        )

    if not blockers:
        return "ACCEPTED", []
    if pr_ready_tasks > 0 or blocked_human_count > 0:
        return "PARTIAL", blockers
    return "REJECTED", blockers


def summarize_routing_contracts(metadata_rows: list[object]) -> dict[str, int]:
    """Count persisted seniority classes from task metadata rows."""
    summary: dict[str, int] = {}
    for raw in metadata_rows:
        try:
            metadata = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(metadata, dict):
            continue
        contract = metadata.get("task_contract")
        if not isinstance(contract, dict):
            continue
        seniority = contract.get("seniority_class")
        if isinstance(seniority, str) and seniority:
            summary[seniority] = summary.get(seniority, 0) + 1
    return summary


def _task_requires_chief(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    complex_terms = (
        "criar, editar, listar",
        "gestão",
        "gestao",
        "itens de trabalho",
        "cada item possui",
        "máquina",
        "maquina",
        "estados",
        "filtros",
        "exportação",
        "exportacao",
        "filtrar",
        "exportar",
        "engenharia",
        "frontend",
        "visualiza",
        "testes",
        "valida",
        "backend",
        "crud",
        "json",
        "pull request",
        "pr artifact",
        "relat",
        "comandos",
    )
    return any(term in text for term in complex_terms)


def apply_api_led_task_contracts(db_path: str) -> dict[str, int]:
    """Annotate imported benchmark tasks so V4 routes complex work to Chief Engineer.

    The PRD extractor keeps numbered product requirements as task-level work and
    stores nested bullets as acceptance criteria. This benchmark layer adds the
    explicit V4 contract expected by MASTER_BACKLOG_V4: complex product, UI, test
    and reporting work is chief-led; simple bounded clauses stay local-assisted.
    """
    summary = {"chief_only": 0, "chief_led": 0, "local_assisted": 0}
    if not os.path.exists(db_path):
        return summary
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, title, description, metadata_json FROM tasks ORDER BY id")
    rows = c.fetchall()
    for task_id, title, description, metadata_raw in rows:
        try:
            metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else (metadata_raw or {})
        except Exception:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}

        if _task_requires_chief(title, description):
            seniority = "chief_led"
            risk_level = "medium"
            allowed_files = [
                "app/sprintboard.html",
                "tests/test_board_rules.py",
                "docs/pr.md",
                "docs/cost_benchmark.md",
                "docs/review.md",
                "docs/risk.md",
            ]
            visual_required = "frontend" in f"{title} {description}".lower() or "visualiza" in f"{title} {description}".lower()
            if visual_required:
                seniority = "chief_only"
                risk_level = "high"
                if "app/sprintboard.html" not in allowed_files:
                    allowed_files.append("app/sprintboard.html")
            summary[seniority] += 1
        else:
            seniority = "local_assisted"
            risk_level = "low"
            allowed_files = ["tests/test_board_rules.py"]
            visual_required = False
            summary["local_assisted"] += 1

        existing_contract = metadata.get("task_contract")
        if not isinstance(existing_contract, dict):
            existing_contract = {}
        metadata["task_contract"] = {
            **existing_contract,
            "allowed_files": allowed_files,
            "visual_required": visual_required,
            "visual_actual_output": "app/sprintboard.html" if visual_required else None,
            "canonical_test_command": "python -m pytest tests/test_board_rules.py -q",
            "seniority_class": seniority,
            "v4_api_led_benchmark": True,
        }
        c.execute(
            "UPDATE tasks SET risk_level = ?, metadata_json = ? WHERE id = ?",
            (risk_level, json.dumps(metadata), task_id),
        )
    conn.commit()
    conn.close()
    return summary

async def run_preflight_checks(v4_dir: str) -> tuple[dict[str, Any], str | None]:
    """Runs all pre-flight diagnostic validations and returns results and the chosen LLM model."""
    results = {}
    
    # 1. Check Docker or Dev Mode (Local Sandbox)
    docker_active, docker_err = await check_docker_status()
    dev_mode = False
    config_path = os.path.join(v4_dir, ".localforge", "config.yaml")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                sandbox_type = cfg.get("sandbox", {}).get("type", "local")
                if sandbox_type == "local":
                    dev_mode = True
        except Exception:
            pass
            
    results["docker_or_dev"] = {
        "passed": docker_active or dev_mode,
        "detail": f"Docker active: {docker_active}, Dev mode (local sandbox) config: {dev_mode}"
    }
    
    # 2. Check LLM model installed in Ollama & select best fallback
    ollama_active, installed_models = await check_ollama_status()
    chosen_model = None
    
    # Preferred order: env model -> config model -> fallback options
    preferred_models = []
    
    if os.environ.get("LOCALFORGE_MODEL"):
        preferred_models.append(os.environ["LOCALFORGE_MODEL"])
    if os.environ.get("OPENROUTER_MODEL"):
        preferred_models.append(os.environ["OPENROUTER_MODEL"])
        
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                default_cfg_model = cfg.get("models", {}).get("default_model")
                if default_cfg_model:
                    preferred_models.append(default_cfg_model)
        except Exception:
            pass
            
    fallback_options = ["gemma4:12b", "granite4.1:8b", "nemotron-3-nano:4b"]
    
    if ollama_active:
        for fo in fallback_options:
            for im in installed_models:
                if fo == im or fo in im or im in fo:
                    chosen_model = im
                    break
            if chosen_model:
                break

        if not chosen_model:
            for pm in preferred_models:
                for im in installed_models:
                    if pm == im or pm in im or im in pm:
                        chosen_model = im
                        break
                if chosen_model:
                    break

    model_passed = chosen_model is not None
    results["llm_installed"] = {
        "passed": model_passed,
        "detail": f"Chosen model for execution: '{chosen_model}'. Ollama installed models: {installed_models}"
    }
    
    chief_config = chief_engineer_config_from_env()
    results["chief_engineer_configured"] = {
        "passed": bool(chief_config.get("model") and chief_config.get("api_key_configured")),
        "detail": (
            f"provider={chief_config.get('provider')}, "
            f"model configured: {bool(chief_config.get('model'))}, "
            f"api key configured: {chief_config.get('api_key_configured')}, "
            f"fallback={chief_config.get('fallback_provider')}"
        ),
    }
    
    return results, chosen_model

async def main():
    source_state = git_source_state()
    print("=== Starting Real LocalForge V4-Only CLI Benchmark Execution ===")
    
    v4_dir = os.path.join(ROOT_DIR, "benchmarks", "workspaces", "sprintboard-v4")
    
    # Clean workspace directory
    if os.path.exists(v4_dir):
        shutil.rmtree(v4_dir)
    os.makedirs(v4_dir, exist_ok=True)

    # Prune git worktrees before running to avoid registration conflicts
    await prune_git_worktrees()

    # Initialize workspace V4
    print("Initializing Workspace V4...")
    await run_cli_command(v4_dir, ["init"])
    v2_prd_path = os.path.join(ROOT_DIR, "docs", "PRD_SPRINTBOARD_LITE.md")
    # PRD import is handled by squad orchestrate

    # Fetch initial tasks count
    v4_db = os.path.join(v4_dir, ".localforge", "localforge.db")
    v4_tasks_imported = 0

    if os.path.exists(v4_db):
        try:
            conn = sqlite3.connect(v4_db)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tasks")
            v4_tasks_imported = c.fetchone()[0]
            conn.close()
        except Exception:
            pass

    routing_contract_summary: dict[str, int] = {}

    # Run Pre-flight Checks
    expected_tasks = 5
    preflight, chosen_model = await run_preflight_checks(v4_dir)
    
    preflight_failed = False
    blockers = []
    for check_name, data in preflight.items():
        print(f"Pre-flight check '{check_name}': {'PASSED' if data['passed'] else 'FAILED'} - {data['detail']}")
        if not data["passed"]:
            preflight_failed = True
            blockers.append(f"Pre-flight '{check_name}' failed: {data['detail']}")

    # Patch config in workspace V4
    docker_active, _ = await check_docker_status()
    chief_config = chief_engineer_config_from_env()
    if chosen_model:
        await patch_workspace_config(v4_dir, chosen_model, docker_active, chief_config)

    v4_run_code, v4_run_out, v4_run_err = -1, "", ""
    
    if all(data["passed"] for data in preflight.values()):
        print("\nPre-flight validation passed! Executing squad orchestrate...")
        v4_run_code, v4_run_out, v4_run_err = await run_cli_command(v4_dir, ["squad", "orchestrate", v2_prd_path])
        print(f"V4 Candidate Run pipeline exit code: {v4_run_code}")
        if v4_run_code != 0:
            print("STDOUT:", v4_run_out)
            print("STDERR:", v4_run_err)
    else:
        print("\n[Blocker] Benchmark execution aborted due to pre-flight failures.")

    # Fetch metrics directly from actual database
    v4_runs_count = 0
    v4_task_runs_count = 0
    v4_calls_logged = 0
    v4_openrouter_calls = 0
    v4_nvidia_calls = 0
    v4_local_calls = 0
    v4_artifacts_logged = 0
    v4_pr_artifacts_logged = 0
    v4_cost_usd = 0.0
    
    task_statuses = {}
    artifact_types = {}

    if os.path.exists(v4_db):
        try:
            conn = sqlite3.connect(v4_db)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM runs")
            v4_runs_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM task_runs")
            v4_task_runs_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM model_call_ledger")
            v4_calls_logged = c.fetchone()[0]

            c.execute("SELECT provider, COUNT(*) FROM model_call_ledger GROUP BY provider")
            for provider, count in c.fetchall():
                if provider == "openrouter":
                    v4_openrouter_calls = count
                elif provider == "nvidia":
                    v4_nvidia_calls = count
                else:
                    v4_local_calls += count
            
            c.execute("SELECT SUM(estimated_cost_usd) FROM model_call_ledger")
            cost_val = c.fetchone()[0]
            v4_cost_usd = float(cost_val) if cost_val else 0.0
            
            c.execute("SELECT COUNT(*) FROM artifacts")
            v4_artifacts_logged = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM artifacts WHERE type = 'PRArtifact'")
            v4_pr_artifacts_logged = c.fetchone()[0]
            
            # Fetch task statuses count
            c.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            for status, count in c.fetchall():
                task_statuses[status] = count
            v4_tasks_imported = sum(task_statuses.values())
                
            # Fetch task contract seniority classes
            c.execute("SELECT metadata_json FROM tasks")
            routing_contract_summary = summarize_routing_contracts(
                [metadata_json for (metadata_json,) in c.fetchall()]
            )

            # Fetch artifact types count
            c.execute("SELECT type, COUNT(*) FROM artifacts GROUP BY type")
            for type_name, count in c.fetchall():
                artifact_types[type_name] = count
                
            conn.close()
        except Exception as e:
            print(f"Failed to query SQLite DB metrics: {e}")

    # Determine status based on actual execution results
    status_classification, status_blockers = classify_benchmark_status(
        preflight_failed=preflight_failed,
        task_statuses=task_statuses,
        expected_tasks=expected_tasks,
        runs_count=v4_runs_count,
        paid_chief_calls=v4_openrouter_calls + v4_nvidia_calls,
        local_model_calls=v4_local_calls,
        pr_artifacts_logged=v4_pr_artifacts_logged,
        run_exit_code=v4_run_code,
        routing_contract_summary=routing_contract_summary,
    )
    blockers.extend(status_blockers)

    execution_error = v4_run_err or v4_run_out
    
    # 1. Format JSON metrics
    metrics_json_path = os.path.join(ROOT_DIR, "docs", "e2e", "v4_only_benchmark_metrics.json")
    metrics_data = {
      "benchmark_name": "SprintBoard Lite V4-Only Empirical Benchmark",
      "date": datetime.now(UTC).strftime("%Y-%m-%d"),
      "prd_file": "docs/PRD_SPRINTBOARD_LITE.md",
      "status": status_classification,
      "blockers": blockers,
      "preflight_checklist": {
          "docker_or_dev_passed": preflight["docker_or_dev"]["passed"],
          "llm_installed_passed": preflight["llm_installed"]["passed"],
          "chief_engineer_configured_passed": preflight["chief_engineer_configured"]["passed"]
      },
      "run_summary": {
          "run_id": f"V4-Run-{v4_runs_count}" if v4_runs_count > 0 else "V4-Run-None",
          "tasks_planned": expected_tasks,
          "tasks_imported": v4_tasks_imported,
          "task_runs_executed": v4_task_runs_count,
          "task_statuses": task_statuses,
          "artifacts_generated": v4_artifacts_logged,
          "artifact_types": artifact_types,
          "model_calls_logged": v4_calls_logged,
          "nvidia_calls_logged": v4_nvidia_calls,
          "openrouter_calls_logged": v4_openrouter_calls,
          "paid_chief_calls_logged": v4_nvidia_calls + v4_openrouter_calls,
          "local_calls_logged": v4_local_calls,
          "estimated_cost_usd": v4_cost_usd,
          "exit_code": v4_run_code,
          "routing_contract_summary": routing_contract_summary
      },
      "conclusions": {
        "quality_score": "Automated gates passed; human review pending" if status_classification == "ACCEPTED" else ("Partial with failures" if status_classification == "PARTIAL" else "Failed/Blocked"),
        "has_pr_artifacts": v4_pr_artifacts_logged > 0,
        "is_auditable": v4_runs_count > 0,
        "human_acceptance": False,
        "api_led_economy_first_exercised": (
          (v4_nvidia_calls + v4_openrouter_calls) > 0
          and v4_local_calls > 0
          and bool(routing_contract_summary)
        )
      }
    }
    with open(metrics_json_path, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    # 2. Format Human Acceptance Report
    acceptance_md_path = os.path.join(ROOT_DIR, "docs", "e2e", "sprintboard_lite_human_acceptance.md")

    has_partial_evidence = status_classification == "PARTIAL"

    acceptance_md = f"""# SprintBoard Lite - Human Acceptance Report

This document records the human validation checks for the **SprintBoard Lite** benchmark.

## PIPELINE STATUS: {status_classification}

## HUMAN STATUS: PENDING REVIEW

Pipeline acceptance means the automated gates completed. It does not mark the generated
product as human-accepted. A reviewer must inspect the runnable deliverable and record their
name/date or review reference separately.

### Acceptance Checklist

- `[ ]` **Create Tasks**: reviewer confirms CRUD in the runnable deliverable.
- `[ ]` **Validation Rules**: reviewer confirms invalid input behavior.
- `[ ]` **Deterministic State Transitions**: reviewer confirms legal and illegal transitions.
- `[ ]` **JSON Export**: reviewer validates exported content.
- `[ ]` **Frontend UI**: reviewer inspects the runnable Kanban UI.
- `[{'x' if status_classification in {'ACCEPTED', 'PARTIAL'} or has_partial_evidence else ' '}]` **Automated Evidence Exists**: runtime artifacts were recorded; this is not human acceptance.

---

## Real Execution Evidence (SQLite & FileSystem)

- **Workspace Path**: `benchmarks/workspaces/sprintboard-v4`
- **Total Task Runs**: {v4_task_runs_count} of {expected_tasks} planned.
- **Total Artifacts**: {v4_artifacts_logged} generated under `.localforge/artifacts/`.
- **Task Statuses**: {json.dumps(task_statuses)}
- **Artifact Types**: {json.dumps(artifact_types)}
- **V4 Routing Contracts**: {json.dumps(routing_contract_summary)}
- **Chief Engineer/NVIDIA Calls**: {v4_nvidia_calls}
- **Chief Engineer/OpenRouter Fallback Calls**: {v4_openrouter_calls}
- **Paid Chief Calls**: {v4_nvidia_calls + v4_openrouter_calls}
- **Local Calls Logged**: {v4_local_calls}
"""
    write_markdown_clean(acceptance_md_path, acceptance_md)

    # 3. Format V4 Only Benchmark Report
    report_md_path = os.path.join(ROOT_DIR, "docs", "e2e", "V4_ONLY_BENCHMARK_REPORT.md")
    
    blockers_list_md = ""
    for i, b in enumerate(blockers, 1):
        blockers_list_md += f"{i}. **{b}**\n"

    report_md = f"""# LocalForge OS - V4-Only Empirical Benchmark Report

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V4 Candidate** (API-led AI Engineering Squad) no workspace isolado `sprintboard-v4`.

O benchmark foi executado de forma física e real para produzir o produto **SprintBoard Lite** de acordo com os requisitos em [docs/PRD_SPRINTBOARD_LITE.md](file:///{ROOT_DIR}/docs/PRD_SPRINTBOARD_LITE.md), sem simulações ou dados pré-fabricados.

### Status do Benchmark
> [!IMPORTANT]
> **STATUS: {status_classification}**
>
> A execução empírica real do LocalForge V4 foi finalizada com classificação **{status_classification}** de acordo com as validações de pré-flight e os resultados persistidos no banco de runtime.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais foram validados pelo pré-flight:

{blockers_list_md if blockers else "Nenhum blocker detectado no pré-flight."}

---

## 3. Métricas Reais do Workspace V4 (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V4 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V4-Run-{v4_runs_count}" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v4/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | {expected_tasks} | Escopo completo do PRD |
| **Tasks Imported** | {v4_tasks_imported} | Sucesso na importação real |
| **Task Runs Executed** | {v4_task_runs_count} | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | {task_statuses.get("PR_READY", 0)} | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | {task_statuses.get("FAILED_SAFE", 0)} | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | ${v4_cost_usd:.4f} | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | {v4_calls_logged} | Quantidade de chamadas aos modelos registradas |
- **PR_READY**: {task_statuses.get("PR_READY", 0)}
- **FAILED_SAFE**: {task_statuses.get("FAILED_SAFE", 0)}
- **BLOCKED_NEEDS_HUMAN_REVIEW**: {task_statuses.get(
    "BLOCKED_NEEDS_HUMAN_REVIEW", 0
)}
| **API-led Routing Contracts** | {json.dumps(routing_contract_summary)} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | {v4_artifacts_logged} | Artefatos gravados no disco pelo pipeline |

---

## 4. Distribuição de Estados das Tarefas

Abaixo consta a distribuição real de status das {expected_tasks} tarefas após a rodada:
- **BACKLOG**: {task_statuses.get("BACKLOG", 0)}
- **READY**: {task_statuses.get("READY", 0)}
- **CLAIMED**: {task_statuses.get("CLAIMED", 0)}
- **PLANNING**: {task_statuses.get("PLANNING", 0)}
- **IMPLEMENTING**: {task_statuses.get("IMPLEMENTING", 0)}
- **TESTING**: {task_statuses.get("TESTING", 0)}
- **PR_READY**: {task_statuses.get("PR_READY", 0)}
- **FAILED_SAFE**: {task_statuses.get("FAILED_SAFE", 0)}

---

## 5. Evidência de Saída do Terminal e Logs da CLI

### Resultados do Pré-flight
- **docker_or_dev**: {"PASSED" if preflight["docker_or_dev"]["passed"] else "FAILED"} - {preflight["docker_or_dev"]["detail"]}
- **llm_installed**: {"PASSED" if preflight["llm_installed"]["passed"] else "FAILED"} - {preflight["llm_installed"]["detail"]}
- **chief_engineer_configured**: {"PASSED" if preflight["chief_engineer_configured"]["passed"] else "FAILED"} - {preflight["chief_engineer_configured"]["detail"]}

### Logs de Execução / Erros da CLI
```text
{execution_error if execution_error else "Executado sem erros de encerramento da CLI principal."}
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: {status_classification}**
> The V4-only run proves the API-led/economy-first architecture only when at least one paid Chief Engineer call (`nvidia` primary or `openrouter` fallback) is recorded in `model_call_ledger` and costs are consolidated in the report. Otherwise the result remains **REJECTED** or **BLOCKED**, even if the CLI exits with code 0.
"""
    write_markdown_clean(report_md_path, report_md)

    evidence_paths = [
        v2_prd_path,
        metrics_json_path,
        acceptance_md_path,
        report_md_path,
    ]
    evidence_manifest = {
        "schema_version": 1,
        "benchmark": "sprintboard-lite-v4",
        "status": status_classification,
        "command": [sys.executable, "scripts/run_benchmark_v4_only.py"],
        "source": source_state,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "evidence": {
            os.path.relpath(path, ROOT_DIR).replace("\\", "/"): sha256_file(path)
            for path in evidence_paths
            if os.path.exists(path)
        },
        "disposable_workspace_committed": False,
        "limitations": [
            "The disposable runtime database and worktrees are intentionally not committed.",
            "Independent human acceptance must be recorded separately from pipeline state.",
        ],
    }
    manifest_path = os.path.join(ROOT_DIR, "docs", "e2e", "v4_evidence_manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence_manifest, handle, indent=2)
        handle.write("\n")

    print(f"\n[Success] V4-Only benchmark execution completed! Status: {status_classification}")

if __name__ == "__main__":
    asyncio.run(main())
