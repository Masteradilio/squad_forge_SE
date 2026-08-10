"""Run the canonical HP12C benchmark in full-access mode with a full trace.

This is a benchmark supervisor, not a second ForgeOS scheduler.  It supplies
the user's PRD, reference image, and one Product Owner instruction, then
delegates all implementation, repair, merge, Tester, and SecurityAuditor work
to the existing HP12C acceptance runner and ForgeOS pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from localforge.observability.run_trace import RunTraceRecorder  # noqa: E402

WORKSPACE_ROOT = ROOT / "benchmarks" / "workspaces"
SAMPLE_DOCS = ROOT / "samples" / "e2e-hp12c-platinum" / "docs"
CHALLENGE_TARGET = "tests/test_hp12c_post_merge_challenge.py"
TESTER_COMMAND = f"python -m pytest {CHALLENGE_TARGET} -q -k complex"
SECURITY_COMMAND = f"python -m pytest {CHALLENGE_TARGET} -q -k security"
PO_INSTRUCTION = (
    "Atue como uma squad autônoma de engenharia para entregar a HP 12C Platinum. "
    "O Tester deve executar o desafio adicional das dez funções mais complexas "
    "(TVM, NPV, IRR, AMORT, SL, SOYD, DB, PRICE, YTM e DATE) usando o comando "
    f"{TESTER_COMMAND!r}. Caprichem na fidelidade visual: reproduzam o chassis, "
    "LCD, posições e nomes dos botões da imagem; legendas brancas ficam na parte "
    "superior dentro do botão, azuis na parte inferior ainda dentro do botão e "
    "laranjas acima do botão, fora dele. O produto deve continuar funcional, "
    "responsivo e autocorrigível sob os gates do ForgeOS."
)


def _default_workspace() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return WORKSPACE_ROOT / f"hp12c-full-access-{stamp}"


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _clean_workspace(workspace: Path) -> None:
    """Start from only the two user inputs inside a validated benchmark path."""

    root = WORKSPACE_ROOT.resolve()
    target = workspace.resolve()
    if target.parent != root or not target.name.startswith("hp12c-full-access-"):
        raise ValueError(f"Refusing to clean an unexpected benchmark path: {target}")
    workspace.mkdir(parents=True, exist_ok=True)
    for child in list(workspace.iterdir()):
        _remove_path(child)
    docs = workspace / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for filename in ("PRD.md", "hp12c_platinum_design_target.png"):
        source = SAMPLE_DOCS / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, docs / filename)


def _snapshot_runtime(workspace: Path, artifact_root: Path) -> list[str]:
    """Preserve raw control-plane, logs, reports, and run files for audit."""

    runtime = workspace / ".localforge"
    copied: list[str] = []
    for directory in (runtime / "control_plane", runtime / "logs", runtime / "runs", runtime / "artifacts" / "reports"):
        if not directory.is_dir():
            continue
        destination = artifact_root / "forgeos-runtime" / directory.relative_to(runtime)
        destination.mkdir(parents=True, exist_ok=True)
        for source in directory.rglob("*"):
            if not source.is_file():
                continue
            target = destination / source.relative_to(directory)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(target.relative_to(artifact_root)).replace("\\", "/"))
    return copied


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--sandbox-type", choices=("docker", "local"), default="docker")
    parser.add_argument("--run-timeout", type=float, default=14400.0)
    args = parser.parse_args()

    workspace = (args.workspace or _default_workspace()).resolve()
    _clean_workspace(workspace)
    trace_dir = workspace.with_name(workspace.name + "-trace")
    if trace_dir.exists():
        _remove_path(trace_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace = RunTraceRecorder(trace_dir / "run_trace.jsonl", run_id=workspace.name, root=ROOT)
    trace.emit(
        "benchmark",
        "run.start",
        payload={
            "benchmark": "HP12C Platinum canonical full_access",
            "workspace": str(workspace),
            "mode": "full_access",
            "inputs": ["docs/PRD.md", "docs/hp12c_platinum_design_target.png"],
            "po_instruction": PO_INSTRUCTION,
            "tester_command": TESTER_COMMAND,
            "security_command": SECURITY_COMMAND,
        },
    )

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT / "backend"),
            "LOCALFORGE_RELEASE_PROMOTION_MODE": "full_access",
            "LOCALFORGE_RELEASE_TESTER_COMMAND": TESTER_COMMAND,
            "LOCALFORGE_RELEASE_SECURITY_COMMAND": SECURITY_COMMAND,
            "LOCALFORGE_RELEASE_OPERATIONAL_PROFILES": "reference",
            "LOCALFORGE_RELEASE_REQUIRE_TREE_AUDIT": "true",
            "LOCALFORGE_RELEASE_REQUIRE_SEMANTIC_REVIEW": "true",
            "LOCALFORGE_RELEASE_POST_MERGE_TIMEOUT": "1200",
            "LOCALFORGE_BENCHMARK_PO_INSTRUCTION": PO_INSTRUCTION,
            # The configured Minimax route currently returns 429 in this
            # environment. Keep it first, then use the live catalog route
            # verified by the benchmark's structured preflight.
            "LOCALFORGE_CLOUD_PREFERRED_ROUTES": (
                "nvidia/minimaxai/minimax-m3,"
                "nvidia/nvidia/nemotron-3-super-120b-a12b,"
                "nvidia/nvidia/nemotron-3-ultra-550b-a55b,"
                "nvidia/nvidia/nemotron-3-nano-30b-a3b"
            ),
        }
    )
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_hp12c_cloud_acceptance.py"),
        "--workspace",
        str(workspace),
        "--sandbox-type",
        args.sandbox_type,
        "--run-timeout",
        str(args.run_timeout),
    ]
    trace.emit("benchmark", "runner.start", payload={"command": command})
    console_path = trace_dir / "runner.console.log"
    return_code = 1
    with console_path.open("w", encoding="utf-8", newline="\n") as console_file:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            console_file.write(line)
            console_file.flush()
            trace.emit("runner", "output", payload={"line": line.rstrip("\r\n")})
        return_code = process.wait()
    trace.emit("benchmark", "runner.end", status="PASS" if return_code == 0 else "FAIL", payload={"exit_code": return_code})

    artifact_root = workspace / ".localforge" / "artifacts" / "hp12c-full-access"
    artifact_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(trace_dir / "run_trace.jsonl", artifact_root / "run_trace.jsonl")
    shutil.copy2(console_path, artifact_root / "runner.console.log")
    copied_runtime = _snapshot_runtime(workspace, artifact_root)
    trace.emit(
        "benchmark",
        "artifacts.snapshot",
        status="PASS" if copied_runtime else "WARN",
        payload={"runtime_files": len(copied_runtime), "artifact_root": str(artifact_root)},
    )
    manifest = {
        "schema": "forgeos.hp12c_full_access_benchmark.v1",
        "benchmark": "HP12C Platinum canonical full_access",
        "workspace": str(workspace),
        "mode": "full_access",
        "exit_code": return_code,
        "inputs": ["docs/PRD.md", "docs/hp12c_platinum_design_target.png"],
        "po_instruction": PO_INSTRUCTION,
        "tester_command": TESTER_COMMAND,
        "security_command": SECURITY_COMMAND,
        "trace": "run_trace.jsonl",
        "runner_console": "runner.console.log",
        "runtime_files": copied_runtime,
    }
    _write_manifest(artifact_root / "manifest.json", manifest)
    trace.emit(
        "benchmark",
        "run.completed" if return_code == 0 else "run.blocked",
        status="PASS" if return_code == 0 else "FAIL",
        payload={"exit_code": return_code, "manifest": str(artifact_root / "manifest.json")},
    )
    # Re-copy the final trace after the terminal events were emitted.
    shutil.copy2(trace_dir / "run_trace.jsonl", artifact_root / "run_trace.jsonl")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
