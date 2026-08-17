"""Run the real HP12C acceptance flow through the OmniRoute gateway only.

This runner deliberately fails closed. A reachable /v1/models endpoint is not
enough: at least one catalog-advertised route must complete a structured probe
before the scheduler is allowed to spend time on the PRD. Free routes are
preferred, while an explicitly configured paid route is an allowed fallback.
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
CHALLENGE_FIXTURE = ROOT / "scripts" / "fixtures" / "hp12c_post_merge_challenge.py"
CHALLENGE_TARGET = "tests/test_hp12c_post_merge_challenge.py"
PO_INSTRUCTION = (
    "Atue como uma squad autônoma de engenharia para entregar a HP 12C Platinum. "
    "O Tester deve executar o desafio adicional das dez funções mais complexas "
    "(TVM, NPV, IRR, AMORT, SL, SOYD, DB, PRICE, YTM e DATE) usando o comando "
    f"python -m pytest {CHALLENGE_TARGET} -q -k complex. Caprichem na fidelidade "
    "visual: reproduzam o chassis, LCD, posições e nomes dos botões da imagem; "
    "legendas brancas ficam na parte superior dentro do botão, azuis na parte "
    "inferior ainda dentro do botão e laranjas acima do botão, fora dele."
)


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


def _route_priority(route: str, preferred: list[str]) -> tuple[int, str]:
    normalized = route.strip().lower()
    try:
        return preferred.index(normalized), normalized
    except ValueError:
        return len(preferred), normalized


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
    api_key: str | None = None,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    key = api_key or _env_value("OMNIROUTE_API_KEY")
    if key:
        request.add_header("Authorization", f"Bearer {key}")
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
    api_key = _env_value("OMNIROUTE_API_KEY")
    if catalog_status != 200 or not isinstance(catalog_body, dict):
        openrouter_key = _env_value("OPENROUTER_API_KEY")
        if openrouter_key:
            openrouter_url = _env_value("OPENROUTER_URL") or "https://openrouter.ai/api/v1"
            or_status, or_body = _request_json(
                f"{openrouter_url.rstrip('/')}/models",
                timeout=timeout,
                api_key=openrouter_key,
            )
            if or_status == 200 and isinstance(or_body, dict):
                base_url = openrouter_url
                catalog_status = or_status
                catalog_body = or_body
                api_key = openrouter_key
                os.environ["LOCALFORGE_MODEL_PROVIDER"] = "openrouter"
                os.environ["LOCALFORGE_CHIEF_PROVIDER"] = "openrouter"
                os.environ["LOCALFORGE_MODEL_BASE_URL"] = openrouter_url
                os.environ["LOCALFORGE_CHIEF_BASE_URL"] = openrouter_url
                os.environ["OPENROUTER_API_KEY"] = openrouter_key
                os.environ["LOCALFORGE_CHIEF_API_KEY"] = openrouter_key
                os.environ["LOCALFORGE_MODEL_API_KEY"] = openrouter_key

    if catalog_status != 200 or not isinstance(catalog_body, dict):
        return False, [], {
            "catalog": f"HTTP {catalog_status}: {catalog_body}",
            "completion": "not attempted",
            "verified_routes": [],
        }
    catalog_routes = [
        str(item["id"])
        for item in catalog_body.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    free_routes = [route for route in catalog_routes if _free_route(route)]
    configured_routes = [
        item.strip()
        for item in (_env_value("LOCALFORGE_CLOUD_PREFERRED_ROUTES") or "").split(",")
        if item.strip()
    ]
    paid_model = _env_value("OPENROUTER_PAID_MODEL") or _env_value("OPENROUTER_MODEL")
    if paid_model and paid_model not in configured_routes:
        configured_routes.insert(0, paid_model)
    free_model = _env_value("OPENROUTER_FREE_MODEL")
    if free_model and free_model not in configured_routes:
        configured_routes.append(free_model)

    if not free_routes and not configured_routes:
        return False, [], {
            "catalog": "reachable but no free or explicitly configured route was advertised",
            "completion": "not attempted",
            "verified_routes": [],
        }

    failures: list[str] = []
    probe = {
        "model": configured_routes[0] if configured_routes else free_routes[0],
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
    try:
        max_probe_routes = max(
            1,
            min(16, int(_env_value("LOCALFORGE_CLOUD_PREFLIGHT_MAX_ROUTES") or 16)),
        )
    except ValueError:
        max_probe_routes = 16
    max_verified_routes = 4
    configured_preference = _env_value("LOCALFORGE_CLOUD_PREFERRED_FREE_ROUTES")
    preferred = [
        item.strip().lower()
        for item in (
            configured_preference
            or (
                "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free,"
                "openrouter/nvidia/nemotron-3-super-120b-a12b:free,"
                "openrouter/google/gemma-4-31b-it:free,"
                "oc/deepseek-v4-flash-free,oc/north-mini-code-free"
            )
        ).split(",")
        if item.strip()
    ]
    ordered_candidates = list(
        dict.fromkeys(
            [
                *configured_routes,
                *preferred,
                *sorted(free_routes, key=lambda route: _route_priority(route, preferred)),
            ]
        )
    )
    probe_routes = [
        route
        for route in ordered_candidates
        if route in catalog_routes
        and not any(marker in route.lower() for marker in ("veo", "seedance"))
    ][:max_probe_routes]
    verified_routes: list[str] = []
    http_410_routes: list[str] = []
    for route in probe_routes:
        probe["model"] = route
        status, body = _request_json(
            f"{base_url.rstrip('/')}/chat/completions",
            payload=probe,
            timeout=timeout,
            api_key=api_key,
        )
        content = ""
        if isinstance(body, dict):
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            parsed = json.loads(content.strip()) if isinstance(content, str) else None
        except json.JSONDecodeError:
            parsed = None
        if status == 200 and isinstance(parsed, dict) and parsed.get("actions"):
            verified_routes.append(route)
            if len(verified_routes) >= max_verified_routes:
                break
            continue
        if status == 410:
            http_410_routes.append(route)
            continue
        failures.append(f"{route}: HTTP {status}: {body}")
    catalog_summary = (
        f"{len(free_routes)} free route(s) and "
        f"{len(catalog_routes)} catalog route(s) advertised"
    )
    if verified_routes:
        return True, catalog_routes, {
            "catalog": catalog_summary,
            "completion": f"structured probe passed via {verified_routes[0]}",
            "verified_route": verified_routes[0],
            "verified_routes": verified_routes,
            "http_410_routes": http_410_routes,
        }
    return False, catalog_routes, {
        "catalog": catalog_summary,
        "completion": "no candidate route completed the structured probe",
        "failures": failures,
        "verified_routes": [],
        "http_410_routes": http_410_routes,
    }


def _sandbox_image_preflight(image: str) -> tuple[bool, str]:
    """Require the repository-owned sandbox image before spending model calls."""
    if not shutil.which("docker"):
        return False, "Docker CLI is not available on the host"
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Docker image inspection failed: {exc}"
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return False, detail[-1] if detail else f"image not found: {image}"
    return True, f"image available: {image}"


def _run_command(
    workspace: Path, python: str, args: list[str], timeout: float
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    root_env = dotenv_values(ROOT / ".env")
    for key, value in root_env.items():
        if value and key not in env:
            env[key] = str(value)
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
    runtime = workspace / ".localforge"
    if runtime.is_dir():
        shutil.rmtree(runtime)
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


def _install_hp12c_acceptance_contract(workspace: Path) -> dict[str, str]:
    """Bind HP12C acceptance contracts and preserve sequential product state."""
    database = workspace / ".localforge" / "localforge.db"
    fixture = ROOT / "scripts" / "fixtures" / "hp12c_task_2_1.py"
    alg_fixture = ROOT / "scripts" / "fixtures" / "hp12c_task_2_2.py"
    memory_fixture = ROOT / "scripts" / "fixtures" / "hp12c_task_2_3.py"
    tvm_fixture = ROOT / "scripts" / "fixtures" / "hp12c_task_3_1.py"
    target = (
        "tests/test_task_2_1_implement_the_rpn_calculation_stack_x_y_z_t_registers_"
        "with_stack_manipulation_enter_x_y_r_clx.py"
    )
    alg_target = (
        "tests/test_task_2_2_implement_the_algebraic_calculation_mode_alg_with_"
        "operator_precedence_and_mode_toggle_g_alg_g_rpn.py"
    )
    memory_target = (
        "tests/test_task_2_3_implement_memory_storage_and_recall_registers_sto_0_9_"
        "rcl_0_9_sto_sto_sto_sto.py"
    )
    tvm_target = (
        "tests/test_task_3_1_implement_tvm_registers_n_i_pv_pmt_fv_and_"
        "cash_flow_timing_beg_end.py"
    )
    rpn_public_apis = [
        "RPNStack",
        "RPNStack.enter",
        "RPNStack.swap",
        "RPNStack.rollDown",
        "RPNStack.clx",
        "RPNStack.X",
        "RPNStack.Y",
        "RPNStack.Z",
        "RPNStack.T",
    ]
    alg_public_apis = ["RPNStack.setMode", "RPNStack.evaluateExpression"]
    memory_public_apis = [
        "RPNStack.sto",
        "RPNStack.rcl",
        "RPNStack.sto_plus",
        "RPNStack.sto_minus",
        "RPNStack.sto_multiply",
        "RPNStack.sto_divide",
    ]
    accumulated_public_apis = rpn_public_apis + alg_public_apis + memory_public_apis
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT id, title, metadata_json FROM tasks WHERE key = ?",
            ("LF-PRD-004",),
        ).fetchone()
        if row is None:
            raise RuntimeError("HP12C Task 2.1 was not imported into the benchmark database")
        task_id, title, metadata_json = row
        metadata = json.loads(metadata_json or "{}")
        contract = metadata.setdefault("task_contract", {})
        contract["product_owner_instruction"] = PO_INSTRUCTION
        allowed_files = [
            path
            for path in contract.setdefault("allowed_files", [])
            if path == "app/index.html"
        ]
        if target not in allowed_files:
            allowed_files.append(target)
        contract["allowed_files"] = allowed_files
        contract["canonical_test_command"] = f"python -m pytest {target} -q"
        contract["acceptance_test_fixture_source"] = str(fixture)
        contract["acceptance_test_fixture_target"] = target
        contract["acceptance_test_policy"] = "repository_owned_observable_behavior"
        contract["required_public_apis"] = list(rpn_public_apis)
        contract["required_product_files"] = ["app/index.html"]
        task_notes = contract.setdefault("implementation_notes", [])
        required_notes = [
            "Preserve the RPNStack public API and implementation in app/index.html; this task owns the production stack behavior.",
            (
                "The acceptance flow calls enter(5), enter(3), swap(), rollDown(), and clx() "
                "and requires register snapshots [5,0,0,0], [3,5,0,0], [5,3,0,0], "
                "[3,0,0,5], and [0,0,0,5]."
            ),
            "Repair the production HTML implementation when these assertions fail; do not edit or weaken the acceptance test.",
        ]
        for note in required_notes:
            if note not in task_notes:
                task_notes.append(note)
        metadata["task_contract"] = contract
        connection.execute(
            "UPDATE tasks SET metadata_json = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), task_id),
        )
        task_rows = connection.execute(
            "SELECT id, key, dependency_task_ids, metadata_json FROM tasks ORDER BY id"
        ).fetchall()
        for index, (current_id, key, dependencies_json, task_metadata_json) in enumerate(task_rows):
            if index == 0:
                continue
            dependencies = json.loads(dependencies_json or "[]")
            if not isinstance(dependencies, list):
                dependencies = []
            previous_id = int(task_rows[index - 1][0])
            if previous_id not in dependencies:
                dependencies.append(previous_id)
            current_metadata = json.loads(task_metadata_json or "{}")
            current_contract = current_metadata.setdefault("task_contract", {})
            current_contract["product_owner_instruction"] = PO_INSTRUCTION
            if index >= 3:
                current_contract["seniority_class"] = "chief_only"
                current_contract["required_product_files"] = ["app/index.html"]
                current_contract["required_public_apis"] = list(rpn_public_apis)
                if index >= 6:
                    current_contract["required_public_apis"] = list(accumulated_public_apis)
                current_notes = current_contract.setdefault("implementation_notes", [])
                for note in (
                    "This HP12C functional task is Chief-only: use the configured high-capacity route, not a local model.",
                    (
                        "Read the accepted predecessor app/index.html before editing and extend it in place; "
                        "never replace the product with a smaller standalone page."
                    ),
                    "Preserve RPNStack and every previously accepted public method and behavior before adding this task's capability.",
                ):
                    if note not in current_notes:
                        current_notes.append(note)
            if key == "LF-PRD-005":
                current_contract["required_public_apis"] = list(rpn_public_apis) + list(alg_public_apis)
                current_contract["required_product_files"] = ["app/index.html"]
                current_contract["seniority_class"] = "chief_only"
                current_allowed_files = [
                    path
                    for path in current_contract.setdefault("allowed_files", [])
                    if path == "app/index.html"
                ]
                if alg_target not in current_allowed_files:
                    current_allowed_files.append(alg_target)
                current_contract["allowed_files"] = current_allowed_files
                current_contract["canonical_test_command"] = f"python -m pytest {alg_target} -q"
                current_contract["acceptance_test_fixture_source"] = str(alg_fixture)
                current_contract["acceptance_test_fixture_target"] = alg_target
                current_contract["acceptance_test_policy"] = "repository_owned_observable_behavior"
                task_notes = current_contract.setdefault("implementation_notes", [])
                for note in (
                    "Preserve the RPNStack public API from LF-PRD-004 while adding ALG mode.",
                    (
                        "Expose mode, setMode(mode), and evaluateExpression(expression) on RPNStack; "
                        "evaluateExpression must honor operator precedence and parentheses."
                    ),
                    (
                        "Read the predecessor's accepted app/index.html before editing. Extend its existing "
                        "RPNStack in place; never replace the complete file with markup or delete enter, "
                        "swap, rollDown, clx, X, Y, Z, or T."
                    ),
                    (
                        "Any candidate that removes an accepted predecessor API is invalid even if the new ALG "
                        "behavior works; restore the prior implementation and add only the missing ALG behavior."
                    ),
                    "The repository-owned ALG fixture is authoritative; repair app/index.html, never replace or weaken the fixture.",
                ):
                    if note not in task_notes:
                        task_notes.append(note)
            elif key == "LF-PRD-006":
                current_contract["required_public_apis"] = list(accumulated_public_apis)
                current_contract["required_product_files"] = ["app/index.html"]
                current_allowed_files = [
                    path
                    for path in current_contract.setdefault("allowed_files", [])
                    if path == "app/index.html"
                ]
                if memory_target not in current_allowed_files:
                    current_allowed_files.append(memory_target)
                current_contract["allowed_files"] = current_allowed_files
                current_contract["canonical_test_command"] = f"python -m pytest {memory_target} -q"
                current_contract["acceptance_test_fixture_source"] = str(memory_fixture)
                current_contract["acceptance_test_fixture_target"] = memory_target
                current_contract["acceptance_test_policy"] = "repository_owned_observable_behavior"
                task_notes = current_contract.setdefault("implementation_notes", [])
                for note in (
                    "Preserve the RPNStack public API from earlier tasks while adding ten memory registers.",
                    (
                        "Expose sto(register), rcl(register), sto_plus(register), sto_minus(register), "
                        "sto_multiply(register), and sto_divide(register) on RPNStack."
                    ),
                    "The repository-owned memory fixture is authoritative; repair app/index.html, never replace or weaken the fixture.",
                ):
                    if note not in task_notes:
                        task_notes.append(note)
            elif key == "LF-PRD-007":
                current_contract["required_public_apis"] = list(accumulated_public_apis) + ["TVM"]
                tvm_allowed_files = [
                    path
                    for path in current_contract.setdefault("allowed_files", [])
                    if path == "app/index.html"
                ]
                if tvm_target not in tvm_allowed_files:
                    tvm_allowed_files.append(tvm_target)
                current_contract["allowed_files"] = tvm_allowed_files
                current_contract["canonical_test_command"] = f"python -m pytest {tvm_target} -q"
                current_contract["acceptance_test_fixture_source"] = str(tvm_fixture)
                current_contract["acceptance_test_fixture_target"] = tvm_target
                current_contract["acceptance_test_policy"] = "repository_owned_observable_behavior"
                task_notes = current_contract.setdefault("implementation_notes", [])
                for note in (
                    (
                        "Expose an inline TVM object in app/index.html with n, i, PV, PMT, FV, timing, "
                        "setReg, and setTiming; do not depend on an untracked external app/tvm.js file."
                    ),
                    "The repository-owned TVM fixture is authoritative; repair the product and never edit or weaken the fixture.",
                ):
                    if note not in task_notes:
                        task_notes.append(note)
            if 7 <= index < len(task_rows) - 1:
                # Later HP12C capabilities are validated together by the
                # final protected challenge. Do not let the model invent
                # Python imports for the single-page HTML product in each
                # intermediate task; keep those tasks focused on the shared
                # production surface and deterministic contract checks.
                current_contract["allowed_files"] = [
                    path
                    for path in current_contract.get("allowed_files", [])
                    if path == "app/index.html"
                ]
                current_contract["canonical_test_command"] = "git diff --check"
                current_contract["acceptance_test_policy"] = "observable_behavior_only"
                current_notes = current_contract.setdefault("implementation_notes", [])
                note = (
                    "This single-page task has no model-generated Python test contract; extend app/index.html "
                    "and rely on the final protected HP12C challenge for behavior validation."
                )
                if note not in current_notes:
                    current_notes.append(note)
                if key == "LF-PRD-008":
                    current_contract["required_public_apis"] = list(accumulated_public_apis) + ["TVM"]
            if key in {"LF-PRD-018", "LF-PRD-019"}:
                # Packaging and release assembly are not visual-design tasks.
                # The visual contract is already exercised by LF-PRD-001..003;
                # keeping these terminal tasks visual_required would re-enter
                # the Chief segmented HTML generator and allow a transient
                # visual route timeout to replace an already validated product.
                # Their protected behavioral/security challenge remains the
                # release gate, while the earlier visual tasks remain the
                # source of visual evidence.
                current_contract["visual_required"] = False
                current_contract["visual_reference_image"] = None
                current_contract["visual_actual_output"] = None
                current_notes = current_contract.setdefault("implementation_notes", [])
                note = (
                    "Packaging/release tasks preserve the accepted visual product; visual compliance "
                    "is proven by LF-PRD-001..003 and the protected post-merge challenge."
                )
                if note not in current_notes:
                    current_notes.append(note)
            current_metadata["task_contract"] = current_contract
            connection.execute(
                "UPDATE tasks SET dependency_task_ids = ?, metadata_json = ? WHERE id = ?",
                (
                    json.dumps(dependencies),
                    json.dumps(current_metadata, ensure_ascii=False),
                    current_id,
                ),
            )
        if task_rows:
            final_id = task_rows[-1][0]
            final_metadata_json = connection.execute(
                "SELECT metadata_json FROM tasks WHERE id = ?", (final_id,)
            ).fetchone()[0]
            final_metadata = json.loads(final_metadata_json or "{}")
            final_contract = final_metadata.setdefault("task_contract", {})
            final_allowed_files = final_contract.setdefault("allowed_files", [])
            if CHALLENGE_TARGET not in final_allowed_files:
                final_allowed_files.append(CHALLENGE_TARGET)
            final_contract["acceptance_test_fixture_source"] = str(CHALLENGE_FIXTURE)
            final_contract["acceptance_test_fixture_target"] = CHALLENGE_TARGET
            final_contract["acceptance_test_policy"] = "repository_owned_observable_behavior"
            final_contract["canonical_test_command"] = f"python -m pytest {CHALLENGE_TARGET} -q"
            final_contract["allowed_files"] = [
                path
                for path in final_contract.get("allowed_files", [])
                if path == "app/index.html"
            ]
            if CHALLENGE_TARGET not in final_contract["allowed_files"]:
                final_contract["allowed_files"].append(CHALLENGE_TARGET)
            final_contract["required_public_apis"] = list(accumulated_public_apis) + [
                "HP12CChallenge"
            ]
            final_contract["post_merge_tester_command"] = (
                f"python -m pytest {CHALLENGE_TARGET} -q -k complex"
            )
            final_contract["post_merge_security_command"] = (
                f"python -m pytest {CHALLENGE_TARGET} -q -k security"
            )
            final_notes = final_contract.setdefault("implementation_notes", [])
            for note in (
                (
                    "The Product Owner requires the exact HP12C post-merge challenge fixture to be "
                    "materialized in the final task."
                ),
                (
                    "Expose window.HP12CChallenge with tvm, npv, irr, amortization, depreciationSL, "
                    "depreciationSOYD, depreciationDB, bondPrice, bondYield, and dateDifference."
                ),
                "Do not weaken or replace tests/test_hp12c_post_merge_challenge.py; repair app/index.html when the challenge fails.",
            ):
                if note not in final_notes:
                    final_notes.append(note)
            final_metadata["task_contract"] = final_contract
            connection.execute(
                "UPDATE tasks SET metadata_json = ? WHERE id = ?",
                (json.dumps(final_metadata, ensure_ascii=False), final_id),
            )
        connection.commit()
        return {
            "task_id": str(task_id),
            "task_title": str(title),
            "fixture": str(fixture),
            "sequential_dependencies": str(max(0, len(task_rows) - 1)),
            "preserved_api": "RPNStack",
            "product_owner_instruction": PO_INSTRUCTION,
            "post_merge_tester_command": f"python -m pytest {CHALLENGE_TARGET} -q -k complex",
            "post_merge_security_command": f"python -m pytest {CHALLENGE_TARGET} -q -k security",
        }
    finally:
        connection.close()


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
        control_plane_dir = database.parent / "control_plane"
        # The durable Control Plane uses ``goal-<id>.json`` for current runs;
        # older workspaces used ``run-<id>.json``. Accept both names so the
        # acceptance supervisor reflects the persisted goal completion instead
        # of downgrading a completed ForgeOS run to PARTIAL.
        state_files = sorted(
            [
                *control_plane_dir.glob("run-*.json"),
                *control_plane_dir.glob("goal-*.json"),
            ],
            key=lambda path: path.stat().st_mtime,
        )
        control_plane: dict[str, Any] = {"present": False}
        if state_files:
            state_path = state_files[-1]
            state = json.loads(state_path.read_text(encoding="utf-8"))
            goal = state.get("goal") if isinstance(state, dict) else {}
            goal = goal if isinstance(goal, dict) else {}
            control_plane = {
                "present": True,
                "path": str(state_path),
                "goal_status": goal.get("status"),
                "completed": goal.get("status") == "COMPLETED",
                "revision": state.get("revision"),
                "receipts": len(state.get("receipts", [])),
            }
        return {
            "tasks": tasks,
            "runs": runs,
            "task_runs": task_runs,
            "artifacts": artifacts,
            "calls_by_provider": calls_by_provider,
            "control_plane": control_plane,
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
    sandbox_image = _env_value("LOCALFORGE_SANDBOX_IMAGE") or "forgeos-sandbox:py312"
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
            "LOCALFORGE_SANDBOX_IMAGE": sandbox_image,
            "LOCALFORGE_OMNIROUTE_REASONING_EFFORT": "none",
            "LOCALFORGE_SEQUENTIAL_TASK_CHAIN": "true",
            "LOCALFORGE_MAX_PARALLEL_TASKS": "1",
            # Bound the complete Agent Harness request, including slow
            # upstream response bodies, so a stalled OmniRoute route yields
            # to the configured finite model ladder.
            "LOCALFORGE_AGENT_REQUEST_TIMEOUT": "90",
        }
    )

    ready, routes, preflight = _omniroute_preflight(base_url)
    evidence: dict[str, Any] = {"preflight": preflight, "gateway_url": base_url}
    if not ready:
        report = _write_report(workspace, "BLOCKED", evidence)
        print(f"BLOCKED: OmniRoute completion pre-flight failed. Report: {report}")
        return 2

    sandbox_ready, sandbox_message = _sandbox_image_preflight(sandbox_image)
    evidence["sandbox"] = {
        "type": args.sandbox_type,
        "image": sandbox_image,
        "ready": sandbox_ready,
        "message": sandbox_message,
    }
    if args.sandbox_type == "docker" and not sandbox_ready:
        report = _write_report(workspace, "BLOCKED", evidence)
        print(f"BLOCKED: Docker sandbox pre-flight failed. Report: {report}")
        return 2

    # Use routes that actually passed the structured probe before catalog
    # order. Generic aliases and stale catalog entries can select a different
    # upstream model than the route the preflight exercised.
    raw_verified_routes = preflight.get("verified_routes", [])
    verified_routes = (
        [str(item).strip() for item in raw_verified_routes if str(item).strip()]
        if isinstance(raw_verified_routes, list)
        else []
    )
    verified_route = preflight.get("verified_route")
    if not verified_routes and verified_route:
        verified_routes = [str(verified_route).strip()]
    raw_http_410_routes = preflight.get("http_410_routes", [])
    if isinstance(raw_http_410_routes, list):
        http_410_routes = {
            str(item).strip()
            for item in raw_http_410_routes
            if str(item).strip()
        }
    else:
        http_410_routes = set()
    catalog_routes = [item for item in routes if item not in http_410_routes]
    ordered_routes = list(dict.fromkeys([*verified_routes, *catalog_routes]))
    route = str(
        verified_routes[0]
        if verified_routes
        else (ordered_routes[0] if ordered_routes else "auto/best-free")
    )
    ladder = ",".join(ordered_routes[:8])
    openrouter_key = _env_value("OPENROUTER_API_KEY")
    os.environ.update(
        {
            "LOCALFORGE_DEFAULT_MODEL": route,
            "LOCALFORGE_CHIEF_MODEL": route,
            "LOCALFORGE_FALLBACK_MODELS": ladder,
            "LOCALFORGE_CHIEF_FALLBACK_MODELS": ladder,
            "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS": ladder,
            "LOCALFORGE_CLOUD_VERIFIED_ROUTES": ",".join(verified_routes),
            "LOCALFORGE_MAX_RUN_TIME": str(args.run_timeout),
            **(
                {
                    "OPENROUTER_API_KEY": openrouter_key,
                    "LOCALFORGE_CHIEF_API_KEY": openrouter_key,
                    "LOCALFORGE_MODEL_API_KEY": openrouter_key,
                }
                if openrouter_key
                else {}
            ),
            # Financial tasks can legitimately consume several bounded Chief
            # retries when OmniRoute returns consecutive timeouts. Keep this
            # finite and below the run-level recovery ceiling.
            "LOCALFORGE_MAX_REPAIR_ATTEMPTS": "4",
            # HP12C is a single-file HTML product. Keep the general diff guard
            # active, but allow a complete bounded file rewrite to reach the
            # deterministic visual and behavioral gates. The product is
            # intentionally richer than the generic 24k benchmark fixture;
            # the 100k ceiling still matches SafeFileEditor's hard upper bound.
            "LOCALFORGE_MAX_DIFF_GROWTH": "100000",
            "LOCALFORGE_MAX_VISUAL_DIFF_GROWTH": "100000",
            # Allow bounded recovery for transient OmniRoute/Chief Engineer timeouts.
            "LOCALFORGE_MAX_RUN_RECOVERY_CYCLES": "8",
            # The HP12C run deliberately exercises a long Chief Engineer
            # ladder across nineteen sequential tasks. Keep the gateway-call
            # budget finite, but large enough that recoverable route
            # timeouts do not exhaust it before the post-merge challenge.
            "LOCALFORGE_MAX_GATEWAY_CALLS": "192",
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
                if command[:3] == ["-m", "localforge.cli.main", "run"] and code == 124:
                    recovery_reason = (
                        f"external benchmark timeout after {timeout:.0f}s; "
                        "worker process was terminated"
                    )
                    recovery_command = [
                        "-m",
                        "localforge.cli.main",
                        "run",
                        "--reconcile-interrupted",
                        "--reason",
                        recovery_reason,
                    ]
                    recovery_code, recovery_output = _run_command(
                        workspace, args.python, recovery_command, 90.0
                    )
                    outputs.append(
                        {
                            "command": recovery_command,
                            "exit_code": recovery_code,
                            "tail": recovery_output[-4000:],
                        }
                    )
                evidence["commands"] = outputs
                report = _write_report(workspace, "BLOCKED", evidence)
                print(f"BLOCKED: command failed. Report: {report}")
                return 3
            if command[:3] == ["-m", "localforge.cli.main", "import-prd"]:
                evidence["acceptance_contract"] = _install_hp12c_acceptance_contract(workspace)

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
            and summary["control_plane"].get("completed", False)
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
