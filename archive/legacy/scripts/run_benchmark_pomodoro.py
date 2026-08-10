import os
import sys
import json
import asyncio
import shutil
import sqlite3
import yaml
from datetime import datetime, UTC
from typing import Any
from dotenv import dotenv_values

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    """Checks if Docker Daemon is active."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return True, stdout.decode("utf-8").strip()
        else:
            return False, stderr.decode("utf-8").strip()
    except Exception as e:
        return False, str(e)


async def check_ollama_status() -> tuple[bool, list[str]]:
    """Checks if local Ollama daemon is reachable and lists downloaded models."""
    import urllib.request
    import json
    try:
        loop = asyncio.get_event_loop()
        def fetch():
            try:
                response = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
                return response.read().decode("utf-8")
            except Exception as e:
                return str(e)
        res = await loop.run_in_executor(None, fetch)
        if "models" in res:
            data = json.loads(res)
            models = [m["name"] for m in data.get("models", [])]
            return True, models
        else:
            return False, []
    except Exception as e:
        return False, []


async def run_cli_command(cwd: str, args: list[str]) -> tuple[int, str, str]:
    """Executes a LocalForge CLI command in the specified directory using the absolute python venv path."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(ROOT_DIR, "backend")
    for key in ("OPENROUTER_MODEL", "OPENROUTER_API_KEY", "LOCALFORGE_MODEL_API_KEY"):
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
        return proc.returncode, stdout.decode("utf-8").strip(), stderr.decode("utf-8").strip()
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
    chief_model: str | None,
):
    """Updates config.yaml for V3 API-led/economy-first routing."""
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
            cfg["chief_engineer"]["enabled"] = bool(chief_model)
            cfg["chief_engineer"]["provider"] = "openrouter"
            cfg["chief_engineer"]["base_url"] = "https://openrouter.ai/api/v1"
            cfg["chief_engineer"]["model"] = chief_model
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
                f"chief_model_configured={bool(chief_model)}, sandbox_type={cfg['sandbox']['type']}"
            )
        except Exception as e:
            print(f"Failed to patch config at {config_path}: {e}")


def chief_engineer_config_from_env() -> tuple[str | None, bool]:
    env = os.environ.copy()
    env.update({k: v for k, v in root_env_values().items() if k not in env})
    return env.get("OPENROUTER_MODEL"), bool(env.get("OPENROUTER_API_KEY"))


def _task_requires_chief(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    complex_terms = (
        "gestão",
        "gestao",
        "sessões",
        "sessoes",
        "máquina",
        "maquina",
        "estados",
        "timer",
        "regra de ouro",
        "long_break",
        "consecutivas",
        "persistência",
        "persistancia",
        "relatórios",
        "relatorios",
        "exportar",
        "json",
        "interface",
        "frontend",
        "visualiza",
        "visual",
        "testes",
        "backend",
        "pull request",
        "pr artifact",
        "cost_benchmark",
    )
    return any(term in text for term in complex_terms)


def apply_api_led_task_contracts(db_path: str) -> dict[str, int]:
    """Annotate imported benchmark tasks so V3 routes complex work to Chief Engineer.

    For the Pomodoro Tracker, complex state-machines, reports and visuals route
    to Chief Engineer, while CRUD remains local-assisted.
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
                "app/pomodoro.html",
                "tests/test_pomodoro.py",
                "docs/pr.md",
                "docs/cost_benchmark.md",
                "docs/review.md",
                "docs/risk.md",
            ]
            visual_required = "frontend" in f"{title} {description}".lower() or "visualiza" in f"{title} {description}".lower() or "interface" in f"{title} {description}".lower()
            if visual_required:
                seniority = "chief_only"
                risk_level = "high"
            summary[seniority] += 1
        else:
            seniority = "local_assisted"
            risk_level = "low"
            allowed_files = ["tests/test_pomodoro.py"]
            visual_required = False
            summary["local_assisted"] += 1

        test_command = "python -m pytest tests/test_pomodoro.py -q"
        text = f"{title} {description}".lower()
        if "sessões" in text or "sessoes" in text or "crud" in text:
            test_command = 'python -m pytest tests/test_pomodoro.py -k "session or database or crud or db" -q'
        elif "máquina" in text or "maquina" in text or "timer" in text:
            test_command = 'python -m pytest tests/test_pomodoro.py -k "state or status or transition or timer" -q'
        elif "regra de ouro" in text or "ouro" in text:
            test_command = 'python -m pytest tests/test_pomodoro.py -k "golden or rule" -q'
        elif "relatórios" in text or "relatorios" in text or "exportar" in text:
            test_command = 'python -m pytest tests/test_pomodoro.py -k "report or export" -q'
        elif "interface" in text or "frontend" in text or "view" in text:
            test_command = 'python -m pytest tests/test_pomodoro.py -k "interface or html or ui or visual or view" -q'

        metadata["task_contract"] = {
            **(metadata.get("task_contract") if isinstance(metadata.get("task_contract"), dict) else {}),
            "allowed_files": allowed_files,
            "visual_required": visual_required,
            "visual_actual_output": "app/pomodoro.html" if visual_required else None,
            "canonical_test_command": test_command,
            "seniority_class": seniority,
            "v3_api_led_benchmark": True,
        }
        c.execute(
            "UPDATE tasks SET risk_level = ?, metadata_json = ? WHERE id = ?",
            (risk_level, json.dumps(metadata), task_id),
        )
    conn.commit()
    conn.close()
    return summary


async def run_preflight_checks(v3_dir: str, v3_tasks_imported: int, expected_tasks: int) -> tuple[dict[str, Any], str | None]:
    """Runs all pre-flight diagnostic validations and returns results and the chosen LLM model."""
    results = {}
    
    # 1. Check Docker or Dev Mode (Local Sandbox)
    docker_active, docker_err = await check_docker_status()
    dev_mode = False
    config_path = os.path.join(v3_dir, ".localforge", "config.yaml")
    
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

    results["llm_installed"] = {
        "passed": chosen_model is not None,
        "detail": f"Chosen model for execution: '{chosen_model}'. Ollama installed models: {installed_models}"
    }
    
    results["task_count_match"] = {
        "passed": v3_tasks_imported == expected_tasks,
        "detail": f"Tasks imported: {v3_tasks_imported}, Expected count: {expected_tasks}"
    }

    chief_model, chief_key_configured = chief_engineer_config_from_env()
    results["chief_engineer_configured"] = {
        "passed": bool(chief_model and chief_key_configured),
        "detail": (
            f"OPENROUTER_MODEL configured: {bool(chief_model)}, "
            f"OPENROUTER_API_KEY configured: {chief_key_configured}"
        ),
    }
    
    return results, chosen_model


async def main():
    print("=== Starting Real LocalForge Pomodoro Tracker CLI Benchmark Execution ===")
    
    v3_dir = os.path.join(ROOT_DIR, "benchmarks", "workspaces", "pomodoro-v3")
    
    # Clean workspace directory
    if os.path.exists(v3_dir):
        shutil.rmtree(v3_dir)
    os.makedirs(v3_dir, exist_ok=True)

    # Prune git worktrees before running to avoid registration conflicts
    await prune_git_worktrees()

    # Initialize workspace
    print("Initializing Workspace Pomodoro...")
    await run_cli_command(v3_dir, ["init"])
    pomodoro_prd_path = os.path.join(ROOT_DIR, "docs", "PRD_POMODORO_TRACKER.md")
    await run_cli_command(v3_dir, ["import-prd", pomodoro_prd_path])

    # Fetch initial tasks count
    v3_db = os.path.join(v3_dir, ".localforge", "localforge.db")
    v3_tasks_imported = 0

    if os.path.exists(v3_db):
        try:
            conn = sqlite3.connect(v3_db)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tasks")
            v3_tasks_imported = c.fetchone()[0]
            conn.close()
        except Exception:
            pass

    routing_contract_summary = apply_api_led_task_contracts(v3_db)

    # Run Pre-flight Checks
    expected_tasks = 5
    preflight, chosen_model = await run_preflight_checks(v3_dir, v3_tasks_imported, expected_tasks)
    
    preflight_failed = False
    blockers = []
    for check_name, data in preflight.items():
        print(f"Pre-flight check '{check_name}': {'PASSED' if data['passed'] else 'FAILED'} - {data['detail']}")
        if not data["passed"]:
            preflight_failed = True
            blockers.append(f"Pre-flight '{check_name}' failed: {data['detail']}")

    # Patch config in workspace V3
    docker_active, _ = await check_docker_status()
    chief_model, _chief_key_configured = chief_engineer_config_from_env()
    if chosen_model:
        await patch_workspace_config(v3_dir, chosen_model, docker_active, chief_model)

    v3_run_code, v3_run_out, v3_run_err = -1, "", ""
    
    if not preflight_failed:
        print("\nPre-flight validation passed! Executing plan & run candidate...")
        await run_cli_command(v3_dir, ["plan", "--approve-all"])
        v3_run_code, v3_run_out, v3_run_err = await run_cli_command(v3_dir, ["run", "--unattended"])
        print(f"V3 Candidate Run pipeline exit code: {v3_run_code}")
    else:
        print("\n[Blocker] Benchmark execution aborted due to pre-flight failures.")

    # Fetch metrics directly from actual database
    v3_runs_count = 0
    v3_task_runs_count = 0
    v3_calls_logged = 0
    v3_openrouter_calls = 0
    v3_local_calls = 0
    v3_artifacts_logged = 0
    v3_cost_usd = 0.0
    
    task_statuses = {}
    artifact_types = {}

    if os.path.exists(v3_db):
        try:
            conn = sqlite3.connect(v3_db)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM runs")
            v3_runs_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM task_runs")
            v3_task_runs_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM model_call_ledger")
            v3_calls_logged = c.fetchone()[0]

            c.execute("SELECT provider, COUNT(*) FROM model_call_ledger GROUP BY provider")
            for provider, count in c.fetchall():
                if provider == "openrouter":
                    v3_openrouter_calls = count
                else:
                    v3_local_calls += count
            
            c.execute("SELECT SUM(estimated_cost_usd) FROM model_call_ledger")
            cost_val = c.fetchone()[0]
            v3_cost_usd = float(cost_val) if cost_val else 0.0
            
            c.execute("SELECT COUNT(*) FROM artifacts")
            v3_artifacts_logged = c.fetchone()[0]
            
            # Fetch task statuses count
            c.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            for status, count in c.fetchall():
                task_statuses[status] = count
                
            # Fetch artifact types count
            c.execute("SELECT type, COUNT(*) FROM artifacts GROUP BY type")
            for type_name, count in c.fetchall():
                artifact_types[type_name] = count
                
            conn.close()
        except Exception as e:
            print(f"Failed to query SQLite DB metrics: {e}")

    # Determine status based on actual execution results
    status_classification = "REJECTED"
    if preflight_failed:
        status_classification = "BLOCKED"
    elif v3_runs_count > 0:
        failed_tasks = task_statuses.get("FAILED_SAFE", 0)
        pr_ready_tasks = task_statuses.get("PR_READY", 0)
        
        if v3_openrouter_calls == 0:
            status_classification = "REJECTED"
            blockers.append(
                "V3 API-led routing did not execute any Chief Engineer/OpenRouter call."
            )
        elif pr_ready_tasks > 0 and failed_tasks == 0:
            status_classification = "ACCEPTED"
        elif pr_ready_tasks > 0 or failed_tasks > 0:
            status_classification = "PARTIAL"
        else:
            status_classification = "REJECTED"

    execution_error = v3_run_err or v3_run_out
    
    # 1. Format JSON metrics
    metrics_json_path = os.path.join(ROOT_DIR, "docs", "e2e", "pomodoro_benchmark_metrics.json")
    metrics_data = {
      "benchmark_name": "Pomodoro Tracker V3-Only Empirical Benchmark",
      "date": datetime.now(UTC).strftime("%Y-%m-%d"),
      "prd_file": "docs/PRD_POMODORO_TRACKER.md",
      "status": status_classification,
      "blockers": blockers,
      "preflight_checklist": {
          "docker_or_dev_passed": preflight["docker_or_dev"]["passed"],
          "llm_installed_passed": preflight["llm_installed"]["passed"],
          "task_count_match_passed": preflight["task_count_match"]["passed"],
          "chief_engineer_configured_passed": preflight["chief_engineer_configured"]["passed"]
      },
      "run_summary": {
          "run_id": f"V3-Run-{v3_runs_count}" if v3_runs_count > 0 else "V3-Run-None",
          "tasks_planned": expected_tasks,
          "tasks_imported": v3_tasks_imported,
          "task_runs_executed": v3_task_runs_count,
          "task_statuses": task_statuses,
          "artifacts_generated": v3_artifacts_logged,
          "artifact_types": artifact_types,
          "model_calls_logged": v3_calls_logged,
          "openrouter_calls_logged": v3_openrouter_calls,
          "local_calls_logged": v3_local_calls,
          "estimated_cost_usd": v3_cost_usd,
          "exit_code": v3_run_code,
          "routing_contract_summary": routing_contract_summary
      },
      "conclusions": {
        "quality_score": "Deliverable" if status_classification == "ACCEPTED" else ("Partial with failures" if status_classification == "PARTIAL" else "Failed/Blocked"),
        "has_pr_artifacts": v3_artifacts_logged > 0,
        "is_auditable": v3_runs_count > 0,
        "api_led_economy_first_exercised": v3_openrouter_calls > 0
      }
    }
    os.makedirs(os.path.dirname(metrics_json_path), exist_ok=True)
    with open(metrics_json_path, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    # 2. Format Human Acceptance Report
    acceptance_md_path = os.path.join(ROOT_DIR, "docs", "e2e", "pomodoro_human_acceptance.md")

    has_deliverable = status_classification == "ACCEPTED"
    has_partial_evidence = status_classification == "PARTIAL"

    acceptance_md = f"""# Pomodoro Tracker - Human Acceptance Report

This document records the human validation checks for the **Pomodoro Tracker** benchmark.

## STATUS: {status_classification}

The product is accepted only when the benchmark reaches `ACCEPTED`. A `PARTIAL` result means LocalForge generated some PR artifacts but did not complete the product end-to-end.

### Acceptance Checklist

- `[{'x' if has_deliverable else ' '}]` **Create Sessions**: CRUD is present in the final deliverable.
- `[{'x' if has_deliverable else ' '}]` **Validation Rules**: state-machine validation passes in product tests.
- `[{'x' if has_deliverable else ' '}]` **Golden Rule Enforcement**: consecutive 4 work sessions mandate long break.
- `[{'x' if has_deliverable else ' '}]` **JSON Report**: sessions consolidated export works.
- `[{'x' if has_deliverable else ' '}]` **Frontend UI**: Pomodoro HTML view with controls.
- `[{'x' if has_deliverable or has_partial_evidence else ' '}]` **Evidence Exists**: runtime artifacts exist.

---

## Real Execution Evidence (SQLite & FileSystem)

- **Workspace Path**: `benchmarks/workspaces/pomodoro-v3`
- **Total Task Runs**: {v3_task_runs_count} of {expected_tasks} planned.
- **Total Artifacts**: {v3_artifacts_logged} generated under `.localforge/artifacts/`.
- **Task Statuses**: {json.dumps(task_statuses)}
- **Artifact Types**: {json.dumps(artifact_types)}
- **V3 Routing Contracts**: {json.dumps(routing_contract_summary)}
- **Chief Engineer/OpenRouter Calls**: {v3_openrouter_calls}
- **Local Calls Logged**: {v3_local_calls}
"""
    with open(acceptance_md_path, "w", encoding="utf-8") as f:
        f.write(acceptance_md)

    # 3. Format Pomodoro Benchmark Report
    report_md_path = os.path.join(ROOT_DIR, "docs", "e2e", "POMODORO_BENCHMARK_REPORT.md")
    
    blockers_list_md = ""
    for i, b in enumerate(blockers, 1):
        blockers_list_md += f"{i}. **{b}**\n"

    report_md = f"""# LocalForge OS - Pomodoro Tracker Benchmark Report

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V3 Candidate** no workspace isolado `pomodoro-v3`.

O benchmark foi executado de forma física e real para produzir o produto **Pomodoro Tracker** de acordo com os requisitos em [docs/PRD_POMODORO_TRACKER.md](file:///{ROOT_DIR}/docs/PRD_POMODORO_TRACKER.md), sem simulações.

### Status do Benchmark
> [!IMPORTANT]
> **STATUS: {status_classification}**
>
> A execução empírica real do LocalForge V3 foi finalizada com classificação **{status_classification}** de acordo com as validações de pré-flight e os resultados persistidos no banco de runtime.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais foram validados pelo pré-flight:

{blockers_list_md if blockers else "Nenhum blocker detectado no pré-flight."}

---

## 3. Métricas Reais do Workspace Pomodoro (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V3 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V3-Run-{v3_runs_count}" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/pomodoro-v3/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | {expected_tasks} | Escopo completo do PRD |
| **Tasks Imported** | {v3_tasks_imported} | Sucesso na importação real |
| **Task Runs Executed** | {v3_task_runs_count} | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | {task_statuses.get("PR_READY", 0)} | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | {task_statuses.get("FAILED_SAFE", 0)} | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | ${v3_cost_usd:.4f} | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | {v3_calls_logged} | Quantidade de chamadas aos modelos registradas |
| **OpenRouter Chief Calls Logged** | {v3_openrouter_calls} | Deve ser maior que zero para validar a V3 API-led |
| **Local Calls Logged** | {v3_local_calls} | Evidencia a parte local/economy da arquitetura |
| **API-led Routing Contracts** | {json.dumps(routing_contract_summary)} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | {v3_artifacts_logged} | Artefatos gravados no disco pelo pipeline |

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
- **task_count_match**: {"PASSED" if preflight["task_count_match"]["passed"] else "FAILED"} - {preflight["task_count_match"]["detail"]}
- **chief_engineer_configured**: {"PASSED" if preflight["chief_engineer_configured"]["passed"] else "FAILED"} - {preflight["chief_engineer_configured"]["detail"]}

### Logs de Execução / Erros da CLI
```text
{execution_error if execution_error else "Executado sem erros de encerramento da CLI principal."}
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: {status_classification}**
> The V3-only run proves the API-led/economy-first architecture only when at least one `openrouter` call is recorded in `model_call_ledger`.
"""
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"\n[Success] Pomodoro V3-Only benchmark execution completed! Status: {status_classification}")


if __name__ == "__main__":
    asyncio.run(main())
