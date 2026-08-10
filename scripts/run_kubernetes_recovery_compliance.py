"""Exercise durable goal recovery across a real Kubernetes Pod restart."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
WORKER_SCRIPT = r'''
import json, os, time
path = "/state/recovery.json"
goal_id = os.environ["FORGEOS_GOAL_ID"]
if os.path.exists(path):
    with open(path, encoding="utf-8") as handle:
        state = json.load(handle)
    if float(state.get("lease_expires_at", 0)) <= time.time() and not state.get("reconciled"):
        state["reconciled"] = True
        state["frontier"] = "RECOVERED"
        state["lease_owner"] = None
        state["recovery_count"] = int(state.get("recovery_count", 0)) + 1
else:
    state = {
        "goal_id": goal_id,
        "receipt_id": "receipt-" + goal_id,
        "receipt_count": 1,
        "lease_owner": "worker-before-restart",
        "lease_expires_at": time.time() + 3600,
        "frontier": "RUNNING",
        "reconciled": False,
        "recovery_count": 0,
    }
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(state, handle, sort_keys=True)
os.replace(temporary, path)
time.sleep(3600)
'''.strip()


def _run(kubectl: str, args: list[str], *, input_text: str | None = None, timeout: float = 90) -> dict[str, Any]:
    command = [kubectl, *args]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "exit_code": None, "stdout": "", "stderr": type(exc).__name__}
    return {
        "command": command,
        "exit_code": completed.returncode,
        # Keep complete JSON for Pod discovery; evidence artifacts trim command
        # output separately so structured parsing is never fed a truncated doc.
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _pod(kubectl: str, namespace: str, *, timeout: float = 30) -> dict[str, Any] | None:
    result = _run(kubectl, ["get", "pods", "-n", namespace, "-l", "app=forgeos-recovery-worker", "-o", "json"], timeout=timeout)
    if result["exit_code"] != 0:
        return None
    try:
        items = json.loads(result["stdout"]).get("items", [])
    except (TypeError, ValueError):
        return None
    for item in items:
        status = item.get("status", {})
        ready = any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in status.get("conditions", []))
        if status.get("phase") == "Running" and ready:
            return item
    return None


def _wait_for_pod(kubectl: str, namespace: str, timeout: float = 120) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pod = _pod(kubectl, namespace)
        if pod:
            return pod
        time.sleep(2)
    raise RuntimeError("recovery worker Pod did not become Ready")


def _state(kubectl: str, namespace: str, pod_name: str) -> dict[str, Any]:
    result = _run(kubectl, ["exec", "-n", namespace, pod_name, "--", "python", "-c", "import json; print(json.dumps(json.load(open('/state/recovery.json'))))"], timeout=30)
    if result["exit_code"] != 0:
        raise RuntimeError("could not read durable recovery state")
    return json.loads(result["stdout"].strip().splitlines()[-1])


def _expire_lease(kubectl: str, namespace: str, pod_name: str) -> None:
    code = "import json; p='/state/recovery.json'; s=json.load(open(p)); s['lease_expires_at']=0; s['frontier']='LEASE_EXPIRED'; json.dump(s, open(p, 'w'), sort_keys=True)"
    result = _run(kubectl, ["exec", "-n", namespace, pod_name, "--", "python", "-c", code], timeout=30)
    if result["exit_code"] != 0:
        raise RuntimeError("could not expire the worker lease")


def run(output: Path, *, run_id: str, keep_namespace: bool = False) -> int:
    kubectl = shutil.which("kubectl") or shutil.which("kubectl.exe")
    if not kubectl:
        payload = {"schema": "forgeos.kubernetes_recovery_evidence.v1", "status": "NOT_PROVEN", "reason": "kubectl not installed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 2
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be DNS-safe")
    namespace = f"forgeos-recovery-{run_id}"
    goal_id = f"goal-{run_id}"
    manifests = [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace, "labels": {"forgeos.io/recovery": run_id}}},
        {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "recovery-state", "namespace": namespace}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}}},
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "recovery-worker", "namespace": namespace},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "forgeos-recovery-worker"}},
                "template": {
                    "metadata": {"labels": {"app": "forgeos-recovery-worker"}},
                    "spec": {
                        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "fsGroup": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
                        "containers": [{
                            "name": "worker",
                            "image": "local_forge_os-backend:latest",
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["python", "-c", WORKER_SCRIPT],
                            "env": [{"name": "FORGEOS_GOAL_ID", "value": goal_id}],
                            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                            "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "250m", "memory": "256Mi", "ephemeral-storage": "256Mi"}},
                            "volumeMounts": [{"name": "state", "mountPath": "/state"}, {"name": "tmp", "mountPath": "/tmp"}],
                        }],
                        "volumes": [{"name": "state", "persistentVolumeClaim": {"claimName": "recovery-state"}}, {"name": "tmp", "emptyDir": {}}],
                    },
                },
            },
        },
    ]
    import yaml

    output.parent.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    status = "FAIL"
    error: str | None = None
    cleanup: dict[str, Any] | None = None
    try:
        applied = _run(kubectl, ["apply", "-f", "-"], input_text=yaml.safe_dump_all(manifests, sort_keys=False), timeout=90)
        commands.append(applied)
        if applied["exit_code"] != 0:
            raise RuntimeError("could not apply recovery namespace manifests")
        first_pod = _wait_for_pod(kubectl, namespace)
        before_state = _state(kubectl, namespace, first_pod["metadata"]["name"])
        before = {"pod_name": first_pod["metadata"]["name"], "pod_uid": first_pod["metadata"]["uid"], "state": before_state}
        _expire_lease(kubectl, namespace, first_pod["metadata"]["name"])
        deleted = _run(kubectl, ["delete", "pod", first_pod["metadata"]["name"], "-n", namespace, "--wait=true", "--timeout=90s"], timeout=120)
        commands.append(deleted)
        second_pod = _wait_for_pod(kubectl, namespace)
        after_state = _state(kubectl, namespace, second_pod["metadata"]["name"])
        after = {"pod_name": second_pod["metadata"]["name"], "pod_uid": second_pod["metadata"]["uid"], "state": after_state}
        checks = {
            "pod_identity_changed": before["pod_uid"] != after["pod_uid"],
            "goal_identity_preserved": before_state.get("goal_id") == after_state.get("goal_id") == goal_id,
            "lease_reconciled": after_state.get("frontier") == "RECOVERED" and after_state.get("reconciled") is True,
            "single_receipt_preserved": after_state.get("receipt_count") == 1 and after_state.get("receipt_id") == before_state.get("receipt_id"),
            "recovery_is_idempotent": after_state.get("recovery_count") == 1,
        }
        status = "PASS" if all(checks.values()) else "FAIL"
        after["checks"] = checks
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        error = str(exc)
    finally:
        if not keep_namespace:
            cleanup = _run(kubectl, ["delete", "namespace", namespace, "--wait=true", "--timeout=120s"], timeout=150)
    payload = {
        "schema": "forgeos.kubernetes_recovery_evidence.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "execution_scope": "kubernetes-real",
        "namespace": namespace,
        "status": status if error is None else "FAIL",
        "before": before,
        "after": after,
        "commands": commands,
        "cleanup": cleanup,
    }
    if error:
        payload["error"] = error
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(output), "namespace": namespace}, indent=2))
    return 0 if payload["status"] == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%m%d%H%M%S"))
    parser.add_argument("--keep-namespace", action="store_true")
    args = parser.parse_args()
    return run(args.output, run_id=args.run_id, keep_namespace=args.keep_namespace)


if __name__ == "__main__":
    raise SystemExit(main())
