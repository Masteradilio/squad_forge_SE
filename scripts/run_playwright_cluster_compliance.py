"""Run the frontend Playwright compliance suite against the live Kubernetes service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_SERVICE = "forgeos-forgeos-cloud-frontend"
DEFAULT_NAMESPACE = "forgeos"
DEFAULT_REMOTE_PORT = 80
DEFAULT_WAIT_TIMEOUT = 90.0


class ClusterComplianceError(RuntimeError):
    """Raised when the live cluster cannot satisfy the E2E preflight contract."""


def _resolve_executable(name: str) -> str | None:
    """Resolve Windows command shims (for example, ``npx.cmd``) explicitly."""

    candidates = [name]
    if os.name == "nt":
        candidates = [f"{name}.cmd", name]
    else:
        candidates = [name, f"{name}.cmd"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _select_local_port() -> int:
    """Ask the operating system for a currently unused loopback port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _probe_document(url: str) -> tuple[bool | None, str]:
    request = Request(url, headers={"Accept": "text/html"})
    try:
        with urlopen(request, timeout=2) as response:
            if 200 <= response.status < 300:
                return True, f"HTTP {response.status}"
            return False, f"HTTP {response.status}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (OSError, TimeoutError, URLError) as exc:
        return None, type(exc).__name__


def _probe_projects(url: str) -> tuple[bool | None, str]:
    """Require the same successful JSON-array backend contract as the E2E tests."""

    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=2) as response:
            if not 200 <= response.status < 300:
                return False, f"HTTP {response.status}"
            try:
                payload = json.loads(response.read())
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False, "invalid JSON"
            if not isinstance(payload, list):
                return False, "JSON payload is not an array"
            return True, f"HTTP {response.status}; JSON array"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (OSError, TimeoutError, URLError) as exc:
        return None, type(exc).__name__


def _wait_for_live_contract(
    process: subprocess.Popen,
    base_url: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_document = "not checked"
    last_projects = "not checked"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ClusterComplianceError(
                "kubectl port-forward exited before the frontend contract became ready"
            )
        document_ok, last_document = _probe_document(f"{base_url}/")
        projects_ok, last_projects = _probe_projects(f"{base_url}/api/projects")
        if document_ok is True and projects_ok is True:
            return
        time.sleep(0.5)
    raise ClusterComplianceError(
        "live frontend/backend preflight failed: "
        f"frontend={last_document}; /api/projects={last_projects}"
    )


def _terminate_process(process: subprocess.Popen | None) -> bool:
    """Terminate the port-forward and escalate only if it does not exit promptly."""

    if process is None:
        return True
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    return process.poll() is not None


def _write_manifest(
    artifact_dir: Path,
    *,
    base_url: str,
    e2e_output_dir: Path,
    html_report_dir: Path,
    playwright_exit_code: int | None,
    port_forward_terminated: bool,
    error: str | None,
) -> None:
    manifest = {
        "schema": "forgeos.playwright_cluster_compliance.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "frontend_base_url": base_url,
        "e2e_output_dir": str(e2e_output_dir),
        "e2e_html_report_dir": str(html_report_dir),
        "playwright_exit_code": playwright_exit_code,
        "port_forward_terminated": port_forward_terminated,
        "status": "PASS" if playwright_exit_code == 0 and error is None else "FAIL",
    }
    if error:
        manifest["error"] = error
    (artifact_dir / "run-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _default_artifact_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "artifacts" / "playwright-cluster-compliance" / stamp


def run(args: argparse.Namespace) -> int:
    kubectl = _resolve_executable("kubectl")
    if not kubectl:
        raise ClusterComplianceError("kubectl was not found on PATH")

    npx = _resolve_executable("npx")
    npm = _resolve_executable("npm")
    if not npx and not npm:
        raise ClusterComplianceError("neither npx nor npm was found on PATH")

    artifact_dir = Path(args.artifact_dir).expanduser().resolve() if args.artifact_dir else _default_artifact_dir()
    e2e_output_dir = artifact_dir / "test-results"
    html_report_dir = artifact_dir / "playwright-report"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    e2e_output_dir.mkdir(parents=True, exist_ok=True)
    html_report_dir.mkdir(parents=True, exist_ok=True)
    port_forward_log = artifact_dir / "kubectl-port-forward.log"

    local_port = _select_local_port()
    base_url = f"http://127.0.0.1:{local_port}"
    command = [
        kubectl,
        "--namespace",
        args.namespace,
        "port-forward",
        f"service/{args.service}",
        f"{local_port}:{args.remote_port}",
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "FRONTEND_BASE_URL": base_url,
            "E2E_OUTPUT_DIR": str(e2e_output_dir),
            "E2E_HTML_REPORT_DIR": str(html_report_dir),
        }
    )
    playwright_command = (
        [npx, "--no-install", "playwright", "test", "--config=e2e/playwright.config.ts"]
        if npx
        else [npm, "run", "e2e"]
    )

    process: subprocess.Popen | None = None
    log_handle = None
    playwright_exit_code: int | None = None
    error: str | None = None
    port_forward_terminated = False
    try:
        log_handle = port_forward_log.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _wait_for_live_contract(process, base_url, args.wait_timeout)
        print(f"Running Playwright desktop and mobile projects against {base_url}")
        playwright_exit_code = subprocess.run(
            playwright_command,
            cwd=FRONTEND_DIR,
            env=environment,
            check=False,
        ).returncode
        return_code = playwright_exit_code
    except KeyboardInterrupt:
        error = "interrupted"
        return_code = 130
    except (OSError, ClusterComplianceError) as exc:
        error = str(exc)
        return_code = 1
    finally:
        port_forward_terminated = _terminate_process(process)
        if log_handle is not None:
            log_handle.close()
        _write_manifest(
            artifact_dir,
            base_url=base_url,
            e2e_output_dir=e2e_output_dir,
            html_report_dir=html_report_dir,
            playwright_exit_code=playwright_exit_code,
            port_forward_terminated=port_forward_terminated,
            error=error,
        )

    if error:
        print(f"Cluster Playwright compliance failed: {error}", file=sys.stderr)
        print(f"Port-forward log: {port_forward_log}", file=sys.stderr)
    print(f"Playwright exit code: {playwright_exit_code}")
    print(f"Artifacts: {artifact_dir}")
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT)
    parser.add_argument("--wait-timeout", type=float, default=DEFAULT_WAIT_TIMEOUT)
    parser.add_argument("--artifact-dir", type=Path)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
