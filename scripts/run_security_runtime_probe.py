"""Collect redacted runtime DAST and Kubernetes hardening evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAMESPACE = "forgeos"
DEFAULT_WORKLOAD = "deployment/forgeos-forgeos-cloud-backend"

POD_PROBE = textwrap.dedent(
    r'''
    import json
    import os
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    def request(path, headers=None, method="GET", body=None):
        request = Request(
            "http://127.0.0.1:8000" + path,
            headers=headers or {},
            method=method,
            data=body,
        )
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read(4096)
                return response.status, raw[:200].decode("utf-8", "replace")
        except HTTPError as error:
            return error.code, ""
        except (URLError, TimeoutError, OSError) as error:
            return 0, type(error).__name__

    token = os.environ.get("LOCALFORGE_API_TOKEN", "")
    authenticated = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "local",
        "X-User-ID": "security-probe",
    }
    checks = {}
    statuses = {}
    statuses["health"] = request("/health")[0]
    statuses["readiness"] = request("/ready")[0]
    statuses["protected_without_identity"] = request("/projects")[0]
    checks["health"] = statuses["health"] == 200
    checks["readiness"] = statuses["readiness"] == 200
    checks["protected_without_identity"] = statuses["protected_without_identity"] in {400, 401, 403}
    project_status, project_body = request("/projects", headers=authenticated)
    statuses["authenticated_project_contract"] = project_status
    checks["authenticated_project_contract"] = project_status == 200 and project_body.lstrip().startswith("[")
    statuses["encoded_path_traversal_rejected"] = request("/%2e%2e/%2e%2e/etc/passwd", headers=authenticated)[0]
    checks["encoded_path_traversal_rejected"] = statuses["encoded_path_traversal_rejected"] in {400, 404, 405}
    statuses["oversized_unknown_payload_rejected"] = request(
        "/__forgeos_dast_payload__",
        headers={"Content-Type": "application/json"},
        method="POST",
        body=b"{" + b"x" * 262144 + b"}",
    )[0]
    checks["oversized_unknown_payload_rejected"] = 400 <= statuses["oversized_unknown_payload_rejected"] < 500
    print(json.dumps({"checks": checks, "statuses": statuses, "status": "PASS" if all(checks.values()) else "FAIL"}))
    ''',
).strip()


def _run(command: list[str], timeout: float = 60) -> tuple[int | None, str, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None, "", type(exc).__name__
    # Preserve complete JSON for structured Kubernetes output; only redacted
    # summaries are persisted below.
    return completed.returncode, completed.stdout, completed.stderr


def run_probe(output: Path, *, namespace: str = DEFAULT_NAMESPACE, workload: str = DEFAULT_WORKLOAD) -> int:
    kubectl = shutil.which("kubectl")
    if not kubectl:
        payload = {
            "schema": "forgeos.security_runtime_probe.v1",
            "status": "NOT_PROVEN",
            "execution_scope": "kubernetes-pod",
            "reason": "kubectl not installed",
        }
    else:
        exit_code, stdout, stderr = _run(
            [kubectl, "exec", "-n", namespace, workload, "--", "python", "-c", POD_PROBE],
            timeout=90,
        )
        try:
            probe = json.loads(stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            probe = {"status": "FAIL", "parse_error": True}
        hardening_exit, hardening_stdout, hardening_stderr = _run(
            [kubectl, "get", "deployment,statefulset", "-n", namespace, "-o", "json"],
            timeout=30,
        )
        hardening = {"status": "FAIL", "checks": {}}
        if hardening_exit == 0:
            try:
                document = json.loads(hardening_stdout)
                deployments = document.get("items", []) if isinstance(document, dict) and "items" in document else [document]
                checks: dict[str, bool] = {}
                for deployment in deployments:
                    pod_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
                    pod_security = pod_spec.get("securityContext", {})
                    checks[f"{deployment.get('metadata', {}).get('name', 'unknown')}.run_as_non_root"] = pod_security.get("runAsNonRoot") is True
                    checks[f"{deployment.get('metadata', {}).get('name', 'unknown')}.no_host_path"] = not any(
                        "hostPath" in volume for volume in pod_spec.get("volumes", [])
                    )
                    for container in pod_spec.get("containers", []):
                        security = container.get("securityContext", {})
                        checks[f"{container.get('name', 'unknown')}.read_only_root"] = security.get("readOnlyRootFilesystem") is True
                        checks[f"{container.get('name', 'unknown')}.drop_all"] = "ALL" in security.get("capabilities", {}).get("drop", [])
                policy_exit, policy_stdout, _ = _run(
                    [kubectl, "get", "networkpolicy", "-n", namespace, "-o", "json"],
                    timeout=30,
                )
                policy_document = json.loads(policy_stdout) if policy_exit == 0 else {}
                policy_items = policy_document.get("items", []) if isinstance(policy_document, dict) else []
                checks["network_policy_present"] = bool(policy_items)
                hardening = {"status": "PASS" if checks and all(checks.values()) else "FAIL", "checks": checks}
            except (TypeError, ValueError, AttributeError, KeyError) as exc:
                hardening = {
                    "status": "FAIL",
                    "checks": {"deployment_json": False},
                    "error_type": type(exc).__name__,
                }
        payload = {
            "schema": "forgeos.security_runtime_probe.v1",
            "status": "PASS" if exit_code == 0 and probe.get("status") == "PASS" and hardening.get("status") == "PASS" else "FAIL",
            "execution_scope": "kubernetes-pod",
            "runtime": probe,
            "hardening": hardening,
            "command_exit_code": exit_code,
            "stderr_summary": stderr[-1000:] if stderr else hardening_stderr[-1000:],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({**payload, "generated_at": datetime.now(UTC).isoformat()}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(output)}, indent=2))
    return 0 if payload["status"] == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".localforge/artifacts/security/runtime_probe.json"))
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--workload", default=DEFAULT_WORKLOAD)
    args = parser.parse_args()
    return run_probe(args.output, namespace=args.namespace, workload=args.workload)


if __name__ == "__main__":
    raise SystemExit(main())
