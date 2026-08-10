"""Run the local security evidence collection for PA-012.

Optional tools are reported as ``NOT_PROVEN`` rather than silently treated as
successful. The script never prints secret values and writes a redacted report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import site
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRIVY_IMAGE = os.getenv("FORGEOS_TRIVY_IMAGE", "aquasec/trivy:0.58.2")
SECURITY_IMAGE = os.getenv("FORGEOS_SECURITY_IMAGE", "local_forge_os-backend:latest")
TRIVY_FS_SKIP_DIRS = (
    "/workspace/.localforge",
    "/workspace/.git",
    "/workspace/.agents",
    "/workspace/.benchmarks",
    "/workspace/.deepeval",
    "/workspace/.gemini",
    "/workspace/.mypy_cache",
    "/workspace/.pytest_cache",
    "/workspace/.ruff_cache",
    "/workspace/.github",
    "/workspace/artifacts",
    "/workspace/benchmarks",
    "/workspace/docs",
    "/workspace/samples",
    "/workspace/frontend/node_modules",
    "/workspace/frontend/dist",
)
SECRET_PATTERNS = (
    re.compile(r"(?:sk|pk)-[A-Za-z0-9]{20,}"),
    re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
IGNORED_PARTS = {"node_modules", ".git", ".venv", "__pycache__", "dist"}


def _run(name: str, command: list[str], cwd: Path, timeout: float = 180.0) -> dict[str, Any]:
    executable = command[0]
    if executable == "npm" and shutil.which("npm.cmd"):
        command = ["npm.cmd", *command[1:]]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"name": name, "command": command, "status": "NOT_PROVEN", "exit_code": None, "stdout": "", "stderr": "tool not installed"}
    except subprocess.TimeoutExpired:
        return {"name": name, "command": command, "status": "TIMEOUT", "exit_code": None, "stdout": "", "stderr": "timeout"}
    return {
        "name": name,
        "command": command,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }


def _tool_path(name: str) -> str | None:
    """Resolve normal and per-user Windows script installations."""

    resolved = shutil.which(name)
    if resolved:
        return resolved
    userbase = Path(site.getuserbase())
    candidates = [
        userbase / "Scripts" / f"{name}.exe",
        userbase / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts" / f"{name}.exe",
    ]
    if sys.platform == "win32":
        candidates.append(Path(sys.executable).parent / f"{name}.exe")
    return next((str(path) for path in candidates if path.is_file()), None)


def _locked_requirements(output: Path) -> Path | None:
    """Export uv.lock so SCA audits the reproducible project graph."""

    export_path = output.parent / "requirements-locked.txt"
    try:
        completed = subprocess.run(
            ["uv", "export", "--format", "requirements-txt", "--no-dev", "--no-hashes"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    export_path.write_text(completed.stdout, encoding="utf-8")
    return export_path


def _trivy_docker_command(*args: str, workspace: bool = False) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
    ]
    if workspace:
        command.extend(("-v", f"{ROOT}:/workspace:ro"))
    command.extend((TRIVY_IMAGE, *args))
    return command


def _secret_findings() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False
    ).stdout.decode("utf-8", errors="replace").split("\0")
    for raw_path in files:
        if not raw_path:
            continue
        path = ROOT / raw_path
        if any(part in IGNORED_PARTS for part in path.parts) or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                is_fixture = (
                    raw_path.startswith("backend/tests/")
                    or raw_path.startswith("docs/")
                ) and any(token in content.lower() for token in ("example", "test_", "test-", "dummy"))
                findings.append({"path": raw_path, "pattern": pattern.pattern, "classification": "fixture" if is_fixture else "blocking"})
    return findings


def run_audit(output: Path) -> int:
    findings = _secret_findings()
    blocking_findings = [item for item in findings if item["classification"] == "blocking"]
    checks = [
        {
            "name": "secret-scan",
            "status": "PASS" if not blocking_findings else "FAIL",
            "findings": findings,
            "blocking_findings": blocking_findings,
        },
        _run("npm-audit", ["npm", "audit", "--audit-level=high", "--json"], ROOT / "frontend"),
    ]
    runtime_output = output.parent / "runtime_probe.json"
    runtime_result = _run(
        "runtime-probe",
        [sys.executable, "scripts/run_security_runtime_probe.py", "--output", str(runtime_output)],
        ROOT,
        timeout=120,
    )
    if runtime_output.is_file():
        try:
            checks.append(json.loads(runtime_output.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            checks.append({"name": "runtime-probe", "status": "FAIL", "exit_code": runtime_result.get("exit_code"), "stderr": runtime_result.get("stderr", "")[-2000:]})
    else:
        checks.append({"name": "runtime-probe", "status": "NOT_PROVEN", "exit_code": runtime_result.get("exit_code"), "stdout": runtime_result.get("stdout", "")[-2000:], "stderr": runtime_result.get("stderr", "")[-2000:]})
    locked_requirements = _locked_requirements(output)
    pip_audit = _tool_path("pip-audit")
    if pip_audit and locked_requirements:
        checks.append(_run("pip-audit", [pip_audit, "-r", str(locked_requirements), "--format", "json"], ROOT, timeout=300))
    else:
        checks.append({"name": "pip-audit", "command": [pip_audit or "pip-audit", "-r", str(locked_requirements or "requirements-locked.txt")], "status": "NOT_PROVEN", "exit_code": None, "stdout": "", "stderr": "pip-audit or uv lock export unavailable"})

    ruff = _tool_path("ruff")
    if ruff:
        checks.append(_run("ruff", [ruff, "check", "backend", "--select", "E9,F63,F7,F82"], ROOT, timeout=300))
    else:
        checks.append({"name": "ruff", "command": ["ruff", "check", "backend"], "status": "NOT_PROVEN", "exit_code": None, "stdout": "", "stderr": "tool not installed"})

    trivy = _tool_path("trivy")
    trivy_fs_args = [
        "fs",
        "--ignore-unfixed",
        "--exit-code",
        "1",
        "--severity",
        "HIGH,CRITICAL",
        "--scanners",
        "vuln,misconfig",
        "--timeout",
        "10m",
    ]
    skip_dirs = (
        TRIVY_FS_SKIP_DIRS
        if not trivy
        else tuple(path.removeprefix("/workspace/") for path in TRIVY_FS_SKIP_DIRS)
    )
    for skip_dir in skip_dirs:
        trivy_fs_args.extend(("--skip-dirs", skip_dir))
    trivy_fs_args.append("." if trivy else "/workspace")
    trivy_fs_command = [trivy, *trivy_fs_args] if trivy else _trivy_docker_command(*trivy_fs_args, workspace=True)
    if trivy or _tool_path("docker"):
        if trivy:
            checks.append(_run("trivy-filesystem", trivy_fs_command, ROOT, timeout=300))
        else:
            checks.append(_run("trivy-filesystem", trivy_fs_command, ROOT, timeout=300))
    else:
        checks.append({"name": "trivy-filesystem", "command": trivy_fs_command, "status": "NOT_PROVEN", "exit_code": None, "stdout": "", "stderr": "trivy and docker are unavailable"})

    docker = _tool_path("docker")
    if docker:
        image_scan = _trivy_docker_command(
            "image",
            "--ignore-unfixed",
            "--exit-code",
            "1",
            "--severity",
            "HIGH,CRITICAL",
            "--scanners",
            "vuln,secret,misconfig",
            SECURITY_IMAGE,
        )
        checks.append(_run("trivy-image", image_scan, ROOT, timeout=420))
    else:
        checks.append({"name": "trivy-image", "command": ["docker", "trivy", SECURITY_IMAGE], "status": "NOT_PROVEN", "exit_code": None, "stdout": "", "stderr": "docker is unavailable"})

    payload = {
        "schema": "forgeos.security_audit.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if all(item.get("status") == "PASS" for item in checks) else "PARTIAL",
        "checks": checks,
        "limitations": [
            "The locked dependency graph and image tag are part of the acceptance evidence.",
            "A clean static scan does not replace runtime DAST or prompt-injection tests.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(output)}, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".localforge/artifacts/security/security_audit.json"))
    return run_audit(parser.parse_args().output)


if __name__ == "__main__":
    raise SystemExit(main())
