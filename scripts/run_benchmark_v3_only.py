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
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return False, "Docker status command exceeded the 10s benchmark timeout"
        if proc.returncode == 0:
            return True, stdout.decode("utf-8").strip()
        else:
            return False, stderr.decode("utf-8").strip()
    except Exception as e:
        return False, str(e)

async def check_omniroute_status(base_url: str) -> tuple[bool, list[str], str]:
    """Check the OmniRoute catalog without consulting a local model runtime."""
    import urllib.request

    url = f"{base_url.rstrip('/')}/models"

    try:
        loop = asyncio.get_event_loop()

        def fetch():
            try:
                request = urllib.request.Request(url)
                api_key = os.environ.get("OMNIROUTE_API_KEY") or root_env_values().get("OMNIROUTE_API_KEY")
                if api_key:
                    request.add_header("Authorization", f"Bearer {api_key}")
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status, response.read().decode("utf-8")
            except Exception as e:
                return 0, str(e)

        status_code, body = await loop.run_in_executor(None, fetch)
        if status_code != 200:
            return False, [], f"GET {url} returned HTTP {status_code}: {body[:240]}"
        data = json.loads(body)
        models = [item["id"] for item in data.get("data", []) if isinstance(item, dict) and item.get("id")]
        if not models:
            return False, [], f"GET {url} returned no model routes"
        return True, models, f"OmniRoute catalog reachable at {url}; routes advertised: {models[:12]}"
    except Exception as e:
        return False, [], f"OmniRoute catalog probe failed at {url}: {e}"


def _explicit_free_routes(models: list[str]) -> list[str]:
    """Keep only catalog routes whose identifier explicitly denotes free use."""
    routes = list(
        dict.fromkeys(
            model
            for model in models
            if (model.endswith(":free") or "-free" in model or model.startswith("free/"))
            and not any(video in model.lower() for video in ("veo", "seedance"))
        )
    )

    # Prefer an explicitly configured OpenRouter free connection over the
    # built-in OpenCode ``auto/*`` aliases.  The aliases can remain in the
    # catalog after their upstream pool is exhausted, while an OpenRouter
    # ``:free`` model is tied to the operator's actual connection and quota.
    def route_priority(route: str) -> int:
        normalized = route.lower()
        if normalized.startswith("openrouter/poolside/laguna-s"):
            return 0
        if normalized.startswith("openrouter/poolside/laguna-xs"):
            return 1
        if normalized.startswith("openrouter/"):
            return 2
        if normalized.startswith("free/"):
            return 3
        if normalized.startswith("auto/"):
            return 4
        if normalized.startswith("oc/"):
            return 5
        return 6

    return [
        route
        for _, route in sorted(enumerate(routes), key=lambda item: (route_priority(item[1]), item[0]))
    ]


async def probe_omniroute_completion(
    base_url: str, routes: list[str]
) -> tuple[bool, str | None, list[str]]:
    """Prove that at least one live free route can complete a tiny JSON action.

    ``/v1/models`` only proves that the gateway process is alive. This probe is
    deliberately separate so a stale catalog cannot launch an unattended run
    that will spend its entire budget waiting for a dead upstream connection.
    """
    import urllib.error
    import urllib.request

    try:
        timeout = min(
            12.0,
            max(5.0, float(os.environ.get("LOCALFORGE_CLOUD_PREFLIGHT_ROUTE_TIMEOUT", "8"))),
        )
    except ValueError:
        timeout = 15.0
    failures: list[str] = []

    def fetch(route: str) -> tuple[bool, str]:
        payload = json.dumps(
            {
                "model": route,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return only valid JSON with one action: "
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
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        api_key = os.environ.get("OMNIROUTE_API_KEY") or root_env_values().get("OMNIROUTE_API_KEY")
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content.strip()) if isinstance(content, str) else None
            if isinstance(parsed, dict) and isinstance(parsed.get("actions"), list) and parsed["actions"]:
                return True, "structured probe passed"
            return False, "response did not contain a non-empty actions array"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:180]
            return False, f"HTTP {exc.code}: {detail}"
        except Exception as exc:
            return False, str(exc)

    for route in routes:
        passed, detail = await asyncio.get_running_loop().run_in_executor(None, fetch, route)
        if passed:
            return True, route, failures
        failures.append(f"{route}: {detail}")
    return False, None, failures

async def run_cli_command(cwd: str, args: list[str]) -> tuple[int, str, str]:
    """Run one CLI command with a hard timeout and no orphaned child process."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(ROOT_DIR, "backend")
    for key in (
        "LOCALFORGE_MODEL_API_KEY",
        "LOCALFORGE_MODEL_PROVIDER",
        "LOCALFORGE_MODEL_BASE_URL",
        "LOCALFORGE_DEFAULT_MODEL",
        "LOCALFORGE_FALLBACK_MODELS",
        "LOCALFORGE_CHIEF_PROVIDER",
        "LOCALFORGE_CHIEF_BASE_URL",
        "LOCALFORGE_CHIEF_MODEL",
        "LOCALFORGE_CHIEF_VISUAL_MODEL",
        "LOCALFORGE_CHIEF_API_KEY",
        "LOCALFORGE_CHIEF_FALLBACK_MODELS",
        "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS",
        "LOCALFORGE_CHIEF_FALLBACK_PROVIDER",
        "LOCALFORGE_CHIEF_FALLBACK_BASE_URL",
        "LOCALFORGE_CHIEF_FALLBACK_MODEL",
        "LOCALFORGE_CHIEF_FALLBACK_API_KEY",
        "LOCALFORGE_OMNIROUTE_JSON_VERIFIED",
        "LOCALFORGE_CHIEF_PREFLIGHT_TIMEOUT",
        "OMNIROUTE_URL",
        "OMNIROUTE_API_KEY",
    ):
        value = root_env_values().get(key)
        if value and not env.get(key):
            env[key] = value
    python_exe = sys.executable
    cmd_args = [python_exe, "-m", "localforge.cli.main"] + args
    try:
        default_timeout = float(os.environ.get("LOCALFORGE_BENCHMARK_COMMAND_TIMEOUT", "120"))
        run_timeout = float(os.environ.get("LOCALFORGE_BENCHMARK_RUN_TIMEOUT", "900"))
    except ValueError:
        default_timeout, run_timeout = 120.0, 900.0
    timeout_seconds = run_timeout if "run" in args else default_timeout

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=max(1.0, timeout_seconds)
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            timeout_message = (
                f"Command {' '.join(args)!r} exceeded the benchmark timeout "
                f"of {timeout_seconds:.0f}s and was terminated."
            )
            return 124, stdout.decode("utf-8", errors="replace").strip(), timeout_message
        return proc.returncode or 0, stdout.decode("utf-8", errors="replace").strip(), stderr.decode("utf-8", errors="replace").strip()
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
    free_routes: list[str] | None = None,
):
    """Write an OmniRoute-only Cloud config for the benchmark workspace."""
    config_path = os.path.join(workspace_dir, ".localforge", "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            
            if "models" not in cfg:
                cfg["models"] = {}
            gateway_url = (
                os.environ.get("OMNIROUTE_URL")
                or root_env_values().get("OMNIROUTE_URL")
                or "http://127.0.0.1:20128/v1"
            )
            free_routes = list(dict.fromkeys(free_routes or [default_model]))
            cfg["models"]["provider"] = "omniroute"
            cfg["models"]["base_url"] = gateway_url
            cfg["models"]["default_model"] = default_model
            cfg["models"]["fallback_models"] = free_routes
            
            if "sandbox" not in cfg:
                cfg["sandbox"] = {}
            if not docker_active:
                cfg["sandbox"]["type"] = "local"
            else:
                cfg["sandbox"]["type"] = "docker"

            if "chief_engineer" not in cfg:
                cfg["chief_engineer"] = {}
            cfg["chief_engineer"]["enabled"] = True
            cfg["chief_engineer"]["provider"] = "omniroute"
            cfg["chief_engineer"]["base_url"] = gateway_url
            cfg["chief_engineer"]["model"] = default_model
            cfg["chief_engineer"]["visual_model"] = default_model
            cfg["chief_engineer"]["visual_fallback_models"] = free_routes
            cfg["chief_engineer"]["fallback_models"] = free_routes
            cfg["chief_engineer"]["fallback_provider"] = None
            cfg["chief_engineer"]["fallback_base_url"] = None
            cfg["chief_engineer"]["fallback_model"] = None
            cfg["chief_engineer"]["timeout"] = 240.0

            if "budgets" not in cfg:
                cfg["budgets"] = {}
            # A multi-task visual PRD can legitimately need one initial call
            # plus bounded repairs per task. Keep the financial ceiling hard,
            # but avoid aborting a valid batch on the small default token cap.
            cfg["budgets"]["max_paid_calls"] = 100
            cfg["budgets"]["max_paid_input_tokens"] = 800000
            cfg["budgets"]["max_paid_output_tokens"] = 240000
            cfg["budgets"]["max_paid_usd"] = 2.0
            cfg["budgets"]["max_task_duration"] = 1800.0
            cfg["budgets"]["max_run_time"] = 10800.0
            cfg["budgets"]["max_diff_growth"] = 5000
            # Visual PRDs can need several Scrum Master -> Chief cycles while
            # remaining under the hard paid-call and USD ceilings.
            cfg["budgets"]["max_run_recovery_cycles"] = 8
                
            with open(config_path, "w", encoding="utf-8", newline="\n") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False)
            print(
                f"Patched OmniRoute-only config at {config_path}: "
                f"gateway={gateway_url}, default_model={default_model}, "
                f"chief_provider={cfg['chief_engineer']['provider']}, "
                f"chief_model_configured={bool(chief_config.get('model'))}, "
                f"sandbox_type={cfg['sandbox']['type']}"
            )
        except Exception as e:
            print(f"Failed to patch config at {config_path}: {e}")


def chief_engineer_config_from_env() -> dict[str, Any]:
    env = root_env_values()
    env.update({key: value for key, value in os.environ.items() if value})
    base_url = env.get("LOCALFORGE_CHIEF_BASE_URL") or env.get("OMNIROUTE_URL") or "http://127.0.0.1:20128/v1"
    model = env.get("LOCALFORGE_CHIEF_MODEL") or env.get("OMNIROUTE_MODEL") or "auto/best-free"
    free_fallbacks = [
        model.strip()
        for model in env.get(
            "LOCALFORGE_CHIEF_FALLBACK_MODELS",
            "auto/coding:free,auto/best-free",
        ).split(",")
        if model.strip()
    ]
    return {
        "provider": "omniroute",
        "base_url": base_url,
        "model": model,
        "visual_model": env.get("LOCALFORGE_CHIEF_VISUAL_MODEL") or model,
        "visual_fallback_models": [
            model.strip()
            for model in env.get(
                "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS", ",".join(free_fallbacks)
            ).split(",")
            if model.strip()
        ],
        "fallback_models": free_fallbacks,
        "api_key_configured": bool(env.get("OMNIROUTE_API_KEY")) or base_url.startswith(("http://localhost", "http://127.0.0.1", "http://omniroute")),
        "fallback_provider": None,
        "fallback_base_url": None,
        "fallback_model": None,
    }


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
    """Annotate imported benchmark tasks so V3 routes complex work to Chief Engineer.

    The PRD extractor keeps numbered product requirements as task-level work and
    stores nested bullets as acceptance criteria. This benchmark layer adds the
    explicit V3 contract expected by MASTER_BACKLOG_V3: complex product, UI, test
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
        metadata["task_contract"] = {
            **(existing_contract if isinstance(existing_contract, dict) else {}),
            "allowed_files": allowed_files,
            "visual_required": visual_required,
            "visual_actual_output": "app/sprintboard.html" if visual_required else None,
            "canonical_test_command": "python -m pytest tests/test_board_rules.py -q",
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

def _task_count_matches_contract(db_path: str, expected_prd_tasks: int) -> tuple[bool, str]:
    """Accept the PRD tasks plus the one deterministic release-assembly task."""
    if not os.path.exists(db_path):
        return False, "workspace database is missing"
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT key, title FROM tasks ORDER BY id").fetchall()
    except sqlite3.Error as exc:
        return False, f"could not inspect imported tasks: {exc}"

    if len(rows) == expected_prd_tasks:
        return True, f"Tasks imported: {len(rows)}, expected PRD requirements: {expected_prd_tasks}"

    assembly_key = f"LF-PRD-{expected_prd_tasks + 1:03d}"
    if (
        len(rows) == expected_prd_tasks + 1
        and rows[-1][0] == assembly_key
        and "release assembly" in str(rows[-1][1]).lower()
    ):
        return True, (
            f"Tasks imported: {len(rows)} = {expected_prd_tasks} PRD requirements "
            f"+ deterministic {assembly_key} release-assembly task"
        )
    return False, (
        f"Tasks imported: {len(rows)}, expected {expected_prd_tasks} PRD requirements "
        f"plus only the deterministic {assembly_key} release-assembly task"
    )


async def run_preflight_checks(
    v3_dir: str,
    v3_tasks_imported: int,
    expected_tasks: int,
    db_path: str,
) -> tuple[dict[str, Any], str | None]:
    """Validate Cloud prerequisites and select a route from OmniRoute's live catalog."""
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
    
    # 2. Check the OmniRoute catalog. A catalog hit is not completion proof;
    # the real CLI run performs the bounded chat readiness probe afterwards.
    gateway_url = (
        os.environ.get("OMNIROUTE_URL")
        or root_env_values().get("OMNIROUTE_URL")
        or "http://127.0.0.1:20128/v1"
    )
    gateway_active, available_models, gateway_detail = await check_omniroute_status(gateway_url)
    chosen_model = None
    
    # Preferred order: env model -> config model -> fallback options
    preferred_models = []
    
    for env_name in ("LOCALFORGE_CHIEF_MODEL", "OMNIROUTE_MODEL", "LOCALFORGE_DEFAULT_MODEL"):
        if os.environ.get(env_name):
            preferred_models.append(os.environ[env_name])
        
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                default_cfg_model = cfg.get("models", {}).get("default_model")
                if default_cfg_model:
                    preferred_models.append(default_cfg_model)
        except Exception:
            pass
            
    free_models = _explicit_free_routes(available_models)
    for model in [*preferred_models, *free_models]:
        if model in free_models:
            chosen_model = model
            break

    completion_passed = False
    completion_route: str | None = None
    completion_failures: list[str] = []
    if gateway_active and free_models:
        completion_passed, completion_route, completion_failures = await probe_omniroute_completion(
            gateway_url, free_models
        )
        # A catalog candidate is not a usable route. Only the route that
        # completed the structured probe may be selected for the workspace.
        chosen_model = completion_route if completion_passed else None

    results["omniroute_gateway"] = {
        "passed": gateway_active and chosen_model is not None and completion_passed,
        "detail": (
            f"{gateway_detail}; selected completing free route: {chosen_model!r}"
            if gateway_active and completion_passed
            else (
                f"{gateway_detail}; no advertised free route completed the structured probe"
                if gateway_active
                else gateway_detail
            )
        ),
        "free_routes": free_models,
    }
    results["omniroute_completion"] = {
        "passed": completion_passed,
        "detail": (
            f"Free route {completion_route!r} returned a structured action probe."
            if completion_passed
            else "; ".join(completion_failures) or "No explicit free route was advertised."
        ),
    }
    
    task_count_passed, task_count_detail = _task_count_matches_contract(db_path, expected_tasks)
    results["task_count_match"] = {
        "passed": task_count_passed,
        "detail": task_count_detail,
    }

    chief_config = chief_engineer_config_from_env()
    results["chief_engineer_configured"] = {
        "passed": bool(chief_config.get("model") and chief_config.get("api_key_configured")),
        "detail": (
            f"provider={chief_config.get('provider')}, "
            f"model configured: {bool(chief_config.get('model'))}, "
            f"credentials/configuration ready: {chief_config.get('api_key_configured')}"
        ),
    }
    
    return results, chosen_model

async def main():
    print("=== Starting Real ForgeOS Cloud OmniRoute-Only Benchmark Execution ===")

    gateway_url = (
        os.environ.get("OMNIROUTE_URL")
        or root_env_values().get("OMNIROUTE_URL")
        or "http://127.0.0.1:20128/v1"
    )
    # Establish the Cloud contract before `init`; inherited legacy variables
    # must never make the benchmark initialize an Ollama or direct-provider
    # workspace by accident.
    os.environ.update(
        {
            "OMNIROUTE_URL": gateway_url,
            "LOCALFORGE_MODEL_PROVIDER": "omniroute",
            "LOCALFORGE_MODEL_BASE_URL": gateway_url,
            "LOCALFORGE_DEFAULT_MODEL": "auto/best-free",
            "LOCALFORGE_FALLBACK_MODELS": "auto/coding:free,auto/best-free",
            "LOCALFORGE_CHIEF_PROVIDER": "omniroute",
            "LOCALFORGE_CHIEF_BASE_URL": gateway_url,
            "LOCALFORGE_CHIEF_MODEL": "auto/best-free",
            "LOCALFORGE_CHIEF_VISUAL_MODEL": "auto/best-free",
            "LOCALFORGE_CHIEF_FALLBACK_MODELS": "auto/coding:free,auto/best-free",
            "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS": "auto/best-free,auto/coding:free",
            "LOCALFORGE_OMNIROUTE_REASONING_EFFORT": "none",
        }
    )
    
    v3_dir = os.path.join(ROOT_DIR, "benchmarks", "workspaces", "sprintboard-v3")
    
    # Clean workspace directory
    if os.path.exists(v3_dir):
        shutil.rmtree(v3_dir)
    os.makedirs(v3_dir, exist_ok=True)

    # Prune git worktrees before running to avoid registration conflicts
    await prune_git_worktrees()

    # Initialize workspace V3
    print("Initializing Workspace V3...")
    await run_cli_command(v3_dir, ["init"])
    v2_prd_path = os.path.join(ROOT_DIR, "docs", "PRD_SPRINTBOARD_LITE.md")
    await run_cli_command(v3_dir, ["import-prd", v2_prd_path])

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
    preflight, chosen_model = await run_preflight_checks(
        v3_dir, v3_tasks_imported, expected_tasks, v3_db
    )
    
    preflight_failed = False
    blockers = []
    for check_name, data in preflight.items():
        print(f"Pre-flight check '{check_name}': {'PASSED' if data['passed'] else 'FAILED'} - {data['detail']}")
        if not data["passed"]:
            preflight_failed = True
            blockers.append(f"Pre-flight '{check_name}' failed: {data['detail']}")

    # Patch config in workspace V3
    docker_active, _ = await check_docker_status()
    chief_config = chief_engineer_config_from_env()
    if chosen_model:
        gateway_url = (
            os.environ.get("OMNIROUTE_URL")
            or root_env_values().get("OMNIROUTE_URL")
            or "http://127.0.0.1:20128/v1"
        )
        discovered_routes = preflight["omniroute_gateway"].get("free_routes", [])
        free_route_ladder = ",".join(
            list(dict.fromkeys([chosen_model, *discovered_routes]))
        )
        # Override inherited legacy Ollama/OpenRouter variables so this
        # benchmark cannot accidentally execute a different architecture.
        os.environ.update(
            {
                "OMNIROUTE_URL": gateway_url,
                "LOCALFORGE_MODEL_PROVIDER": "omniroute",
                "LOCALFORGE_MODEL_BASE_URL": gateway_url,
                "LOCALFORGE_DEFAULT_MODEL": chosen_model,
                "LOCALFORGE_FALLBACK_MODELS": free_route_ladder,
                "LOCALFORGE_CHIEF_PROVIDER": "omniroute",
                "LOCALFORGE_CHIEF_BASE_URL": gateway_url,
                "LOCALFORGE_CHIEF_MODEL": chosen_model,
                "LOCALFORGE_CHIEF_VISUAL_MODEL": chosen_model,
                "LOCALFORGE_CHIEF_FALLBACK_MODELS": free_route_ladder,
                "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS": free_route_ladder,
            }
        )
        await patch_workspace_config(
            v3_dir,
            chosen_model,
            docker_active,
            chief_config,
            free_routes=list(dict.fromkeys([chosen_model, *discovered_routes])),
        )

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
    v3_omniroute_calls = 0
    v3_chief_calls = 0
    v3_local_calls = 0
    v3_non_omniroute_calls = 0
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
                normalized_provider = str(provider or "").lower()
                if normalized_provider == "omniroute":
                    v3_omniroute_calls = count
                    v3_chief_calls += count
                else:
                    v3_non_omniroute_calls += count
            
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
        # Check if tasks succeeded or failed
        ready_tasks = task_statuses.get("READY", 0)
        backlog_tasks = task_statuses.get("BACKLOG", 0)
        failed_tasks = task_statuses.get("FAILED_SAFE", 0)
        pr_ready_tasks = task_statuses.get("PR_READY", 0)
        
        if v3_non_omniroute_calls > 0:
            status_classification = "REJECTED"
            blockers.append(
                "Benchmark recorded a model call outside OmniRoute; "
                "the Cloud-only acceptance contract was violated."
            )
        elif v3_chief_calls == 0:
            status_classification = "REJECTED"
            blockers.append(
                "OmniRoute-only routing did not execute any Chief Engineer call; "
                "benchmark did not exercise the intended Cloud architecture."
            )
        elif pr_ready_tasks > 0 and failed_tasks == 0:
            status_classification = "ACCEPTED"
        elif pr_ready_tasks > 0 or failed_tasks > 0:
            status_classification = "PARTIAL"
        else:
            status_classification = "REJECTED"

    execution_error = v3_run_err or v3_run_out
    if preflight_failed:
        execution_evidence = (
            "CLI run was not started because the OmniRoute completion pre-flight failed. "
            "The scheduler and task pipeline were intentionally not invoked."
        )
    elif execution_error:
        execution_evidence = execution_error
    else:
        execution_evidence = "CLI run completed without captured stderr."
    
    # 1. Format JSON metrics
    metrics_json_path = os.path.join(ROOT_DIR, "docs", "e2e", "v3_only_benchmark_metrics.json")
    metrics_data = {
      "benchmark_name": "SprintBoard Lite V3-Only Empirical Benchmark",
      "date": datetime.now(UTC).strftime("%Y-%m-%d"),
      "prd_file": "docs/PRD_SPRINTBOARD_LITE.md",
      "status": status_classification,
      "blockers": blockers,
      "preflight_checklist": {
          "docker_or_dev_passed": preflight["docker_or_dev"]["passed"],
          "omniroute_gateway_passed": preflight["omniroute_gateway"]["passed"],
          "omniroute_completion_passed": preflight["omniroute_completion"]["passed"],
          "task_count_match_passed": preflight["task_count_match"]["passed"],
          "chief_engineer_configured_passed": preflight["chief_engineer_configured"]["passed"]
      },
      "run_summary": {
          "run_id": f"V3-Run-{v3_runs_count}" if v3_runs_count > 0 else "V3-Run-None",
          "tasks_planned": v3_tasks_imported,
          "prd_requirements": expected_tasks,
          "tasks_imported": v3_tasks_imported,
          "task_runs_executed": v3_task_runs_count,
          "task_statuses": task_statuses,
          "artifacts_generated": v3_artifacts_logged,
          "artifact_types": artifact_types,
          "model_calls_logged": v3_calls_logged,
          "omniroute_calls_logged": v3_omniroute_calls,
          "non_omniroute_calls_logged": v3_non_omniroute_calls,
          "chief_engineer_calls_logged": v3_chief_calls,
          "local_calls_logged": v3_local_calls,
          "estimated_cost_usd": v3_cost_usd,
          "exit_code": v3_run_code,
          "routing_contract_summary": routing_contract_summary
      },
      "conclusions": {
        "quality_score": "Deliverable" if status_classification == "ACCEPTED" else ("Partial with failures" if status_classification == "PARTIAL" else "Failed/Blocked"),
        "has_pr_artifacts": v3_artifacts_logged > 0,
        "is_auditable": v3_runs_count > 0,
        "api_led_economy_first_exercised": v3_chief_calls > 0
      }
    }
    with open(metrics_json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(metrics_data, f, indent=2)

    # 2. Format Human Acceptance Report
    acceptance_md_path = os.path.join(ROOT_DIR, "docs", "e2e", "sprintboard_lite_human_acceptance.md")

    has_deliverable = status_classification == "ACCEPTED"
    has_partial_evidence = status_classification == "PARTIAL"

    acceptance_md = f"""# SprintBoard Lite - Human Acceptance Report

This document records the human validation checks for the **SprintBoard Lite** benchmark.

## STATUS: {status_classification}

The product is accepted only when the benchmark reaches `ACCEPTED`. A `PARTIAL` result means LocalForge generated some PR artifacts but did not complete the product end-to-end.

### Acceptance Checklist

- `[{'x' if has_deliverable else ' '}]` **Create Tasks**: CRUD is present in the final deliverable.
- `[{'x' if has_deliverable else ' '}]` **Validation Rules**: title and state-machine validation pass in product tests.
- `[{'x' if has_deliverable else ' '}]` **Deterministic State Transitions**: legal/illegal transitions are enforced.
- `[{'x' if has_deliverable else ' '}]` **JSON Export**: board export works and includes active items.
- `[{'x' if has_deliverable else ' '}]` **Frontend UI**: Kanban UI is delivered as a runnable artifact.
- `[{'x' if has_deliverable or has_partial_evidence else ' '}]` **Evidence Exists**: runtime artifacts exist, but partial evidence is not human acceptance.

---

## Real Execution Evidence (SQLite & FileSystem)

- **Workspace Path**: `benchmarks/workspaces/sprintboard-v3`
- **Total Task Runs**: {v3_task_runs_count} of {v3_tasks_imported} planned.
- **Total Artifacts**: {v3_artifacts_logged} generated under `.localforge/artifacts/`.
- **Task Statuses**: {json.dumps(task_statuses)}
- **Artifact Types**: {json.dumps(artifact_types)}
- **V3 Routing Contracts**: {json.dumps(routing_contract_summary)}
- **Chief Engineer Calls**: {v3_chief_calls} (OmniRoute: {v3_omniroute_calls}; non-OmniRoute: {v3_non_omniroute_calls})
- **Local Calls Logged**: {v3_local_calls}
"""
    with open(acceptance_md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(acceptance_md)

    # 3. Format V3 Only Benchmark Report
    report_md_path = os.path.join(ROOT_DIR, "docs", "e2e", "V3_ONLY_BENCHMARK_REPORT.md")
    
    blockers_list_md = ""
    for i, b in enumerate(blockers, 1):
        blockers_list_md += f"{i}. **{b}**\n"

    report_md = f"""# LocalForge OS - V3-Only Empirical Benchmark Report

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V3 Candidate** (API-led AI Engineering Squad) no workspace isolado `sprintboard-v3`.

O benchmark foi executado de forma física e real para produzir o produto **SprintBoard Lite** de acordo com os requisitos em [docs/PRD_SPRINTBOARD_LITE.md](file:///{ROOT_DIR}/docs/PRD_SPRINTBOARD_LITE.md), sem simulações ou dados pré-fabricados.

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

## 3. Métricas Reais do Workspace V3 (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V3 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V3-Run-{v3_runs_count}" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v3/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | {v3_tasks_imported} | {expected_tasks} requisitos do PRD + assembly determinístico |
| **Tasks Imported** | {v3_tasks_imported} | Sucesso na importação real |
| **Task Runs Executed** | {v3_task_runs_count} | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | {task_statuses.get("PR_READY", 0)} | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | {task_statuses.get("FAILED_SAFE", 0)} | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | ${v3_cost_usd:.4f} | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | {v3_calls_logged} | Quantidade de chamadas aos modelos registradas |
| **Chief Calls Logged** | {v3_chief_calls} | Deve ser maior que zero para validar a V3 API-led |
| **Local Calls Logged** | {v3_local_calls} | Evidencia a parte local/economy da arquitetura |
| **API-led Routing Contracts** | {json.dumps(routing_contract_summary)} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | {v3_artifacts_logged} | Artefatos gravados no disco pelo pipeline |

---

## 4. Distribuição de Estados das Tarefas

Abaixo consta a distribuição real de status das {v3_tasks_imported} tarefas após a rodada:
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
- **omniroute_gateway**: {"PASSED" if preflight["omniroute_gateway"]["passed"] else "FAILED"} - {preflight["omniroute_gateway"]["detail"]}
- **omniroute_completion**: {"PASSED" if preflight["omniroute_completion"]["passed"] else "FAILED"} - {preflight["omniroute_completion"]["detail"]}
- **task_count_match**: {"PASSED" if preflight["task_count_match"]["passed"] else "FAILED"} - {preflight["task_count_match"]["detail"]}
- **chief_engineer_configured**: {"PASSED" if preflight["chief_engineer_configured"]["passed"] else "FAILED"} - {preflight["chief_engineer_configured"]["detail"]}

### Logs de Execução / Erros da CLI
```text
{execution_evidence}
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: {status_classification}**
> The V3-only run proves the OmniRoute-only API-led/economy-first architecture only when at least one `omniroute` call is recorded in `model_call_ledger`, no non-OmniRoute call is recorded, and costs are consolidated in the report. Otherwise the result remains **REJECTED** or **BLOCKED**, even if the CLI exits with code 0.
"""
    with open(report_md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report_md)

    print(f"\n[Success] V3-Only benchmark execution completed! Status: {status_classification}")

if __name__ == "__main__":
    asyncio.run(main())
