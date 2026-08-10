"""Collect bounded recovery evidence without claiming local tests are Kubernetes.

The local mode exercises the durable control-plane fixture in a temporary
directory. The Kubernetes modes are read-only observers: they capture Pod and
Job state, then reconcile it with a prior snapshot. They never delete a
namespace, restart a Pod, roll back a release, or read Secret values.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from localforge.control_plane import (  # noqa: E402
    ControlPlaneKernel,
    ControlPlaneStore,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
    TurnRoute,
)
from scripts.probe_redis import probe_fail_closed  # noqa: E402

SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)"
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)")


def redact_text(value: str) -> str:
    value = URL_CREDENTIAL_PATTERN.sub(r"\1***\3", value)
    return SECRET_PATTERN.sub(r"\1\2***", value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _status(checks: dict[str, dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in checks.values()}
    if statuses == {"PASS"}:
        return "PASS"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    return "NOT_PROVEN"


def _expire_claimed_turn(store: ControlPlaneStore) -> None:
    def mutate(state: Any) -> Any:
        if state is None:
            raise RuntimeError("control-plane state disappeared during recovery fixture")
        state.todos[0].lease_expires_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        return state

    store.update(mutate, operation_id="k8s-recovery-fixture:expire-lease")


def run_local_fixture() -> dict[str, Any]:
    """Run the product control-plane recovery semantics in isolated temp state."""
    with tempfile.TemporaryDirectory(prefix="forgeos-recovery-") as temporary:
        state_path = Path(temporary) / "control_plane.json"
        store = ControlPlaneStore(state_path)
        kernel = ControlPlaneKernel(store)
        goal_id = f"k8s-recovery-fixture:{uuid.uuid4().hex}"
        try:
            kernel.start(
                goal_id=goal_id,
                vision="prove bounded recovery semantics",
                non_negotiables=["no duplicate receipt", "preserve goal identity"],
                tasks=[TaskSnapshot(todo_id="A", title="interrupted lane", status="READY")],
                max_attempts_per_todo=3,
                max_turns=6,
            )
            first = kernel.next_turn("worker-before-restart", lease_seconds=1)
            if first.route != TurnRoute.READY or not first.todo_id or not first.turn_id:
                raise RuntimeError("fixture did not claim a turn")
            _expire_claimed_turn(store)

            restarted_store = ControlPlaneStore(state_path)
            restarted = ControlPlaneKernel(restarted_store)
            recovered = restarted.next_turn("worker-after-restart", lease_seconds=1)
            lease_ok = recovered.route == TurnRoute.READY and recovered.todo_id == "A"
            identity_before = store.read()
            identity_after = restarted_store.read()
            identity_ok = bool(
                identity_before
                and identity_after
                and identity_before.goal.goal_id == identity_after.goal.goal_id == goal_id
            )

            if not lease_ok:
                raise RuntimeError("expired lease was not reconciled")
            completed = restarted.record_result(
                TurnResult(
                    todo_id="A",
                    turn_id=recovered.turn_id or "missing",
                    result_kind=TurnResultKind.VALIDATED_COMPLETION,
                    summary="recovered after lease expiry",
                    validated_by="worker-after-restart",
                    idempotency_key="k8s-recovery-fixture:completion",
                )
            )
            duplicate = restarted.record_result(
                TurnResult(
                    todo_id="A",
                    turn_id=recovered.turn_id or "missing",
                    result_kind=TurnResultKind.VALIDATED_COMPLETION,
                    summary="recovered after lease expiry",
                    validated_by="worker-after-restart",
                    idempotency_key="k8s-recovery-fixture:completion",
                )
            )
            journal_ok = restarted.store.verify_replay()
            checks = {
                "lease_expiry": {
                    "status": "PASS" if lease_ok else "BLOCKED",
                    "reason": "expired claimed turn was returned to the frontier",
                },
                "restart_reconciliation": {
                    "status": "PASS" if identity_ok and journal_ok else "BLOCKED",
                    "reason": "new kernel instance resumed the same persisted goal and journal",
                },
                "idempotent_writeback": {
                    "status": "PASS" if len(duplicate.receipts) == len(completed.receipts) else "BLOCKED",
                    "reason": "duplicate result did not create an additional receipt",
                },
                "fail_closed": {
                    "status": "PASS"
                    if asyncio.run(probe_fail_closed("redis://127.0.0.1:63999/0"))
                    else "BLOCKED",
                    "reason": "unavailable Redis endpoint did not grant a write or lease",
                },
            }
        except Exception as exc:
            reason = f"{type(exc).__name__}: {redact_text(str(exc))}"
            checks = {
                "lease_expiry": {"status": "BLOCKED", "reason": reason},
                "restart_reconciliation": {"status": "BLOCKED", "reason": reason},
                "idempotent_writeback": {"status": "BLOCKED", "reason": reason},
                "fail_closed": {"status": "NOT_PROVEN", "reason": "fixture stopped before live Redis check"},
            }

        return {
            "schema": "forgeos.recovery_evidence.v1",
            "collected_at": _now(),
            "execution_scope": "local-fixture",
            "kubernetes_real": False,
            "status": _status(checks),
            "checks": checks,
            "limitations": [
                "This temporary control-plane fixture is not a Kubernetes Pod restart.",
                "Run the capture/reconcile modes with Kubernetes evidence before making a cluster recovery claim.",
            ],
        }


def _run_read_only(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": [redact_text(part) for part in command],
        "exit_code": result.returncode,
        "stdout": redact_text(result.stdout),
        "stderr": redact_text(result.stderr),
    }


def _kubectl_json(*args: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    command = ["kubectl", *args]
    observed = _run_read_only(command)
    if observed["exit_code"] != 0:
        return None, observed
    try:
        payload = json.loads(observed["stdout"])
    except json.JSONDecodeError:
        observed["parse_error"] = "kubectl output was not JSON"
        return None, observed
    return payload if isinstance(payload, dict) else None, observed


def _compact_pods(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    pods = payload.get("items", []) if payload else []
    compact: list[dict[str, Any]] = []
    for pod in pods:
        status = pod.get("status", {})
        containers = status.get("containerStatuses", [])
        compact.append(
            {
                "name": pod.get("metadata", {}).get("name"),
                "uid": pod.get("metadata", {}).get("uid"),
                "created_at": pod.get("metadata", {}).get("creationTimestamp"),
                "labels": {
                    key: value
                    for key, value in pod.get("metadata", {}).get("labels", {}).items()
                    if key.startswith("forgeos.io/") or key == "app.kubernetes.io/component"
                },
                "phase": status.get("phase"),
                "restarts": sum(int(item.get("restartCount", 0)) for item in containers),
            }
        )
    return compact


def capture_kubernetes(namespace: str, selector: str) -> dict[str, Any]:
    pods, pods_command = _kubectl_json("get", "pods", "-n", namespace, "-l", selector, "-o", "json")
    jobs, jobs_command = _kubectl_json("get", "jobs", "-n", namespace, "-o", "json")
    events, events_command = _kubectl_json(
        "get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "-o", "json"
    )
    commands = [pods_command, jobs_command, events_command]
    command_failures = [item for item in commands if item["exit_code"] != 0]
    return {
        "schema": "forgeos.recovery_snapshot.v1",
        "collected_at": _now(),
        "execution_scope": "kubernetes-cluster-observation",
        "kubernetes_real": not command_failures,
        "namespace": namespace,
        "selector": selector,
        "pods": _compact_pods(pods),
        "jobs": jobs.get("items", []) if jobs else [],
        "events": [
            {
                "type": item.get("type"),
                "reason": item.get("reason"),
                "message": redact_text(str(item.get("message", ""))),
                "last_timestamp": item.get("lastTimestamp") or item.get("eventTime"),
            }
            for item in (events.get("items", []) if events else [])
        ],
        "commands": commands,
        "status": "PASS" if not command_failures else "BLOCKED",
        "limitations": [
            "Capture is read-only and does not itself interrupt or restart a Pod.",
            "Secret values are not queried or persisted.",
        ],
    }


def _load_status(path: Path | None, expected_scope: str | None = None) -> str | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if expected_scope and payload.get("execution_scope") != expected_scope:
        return None
    if payload.get("status") == "PASS":
        return "PASS"
    return None


def reconcile_kubernetes(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    lease_evidence: Path | None = None,
    redis_evidence: Path | None = None,
) -> dict[str, Any]:
    before_by_name = {item.get("name"): item for item in before.get("pods", [])}
    after_by_name = {item.get("name"): item for item in after.get("pods", [])}
    uid_changed = any(
        before_by_name.get(name, {}).get("uid") != item.get("uid")
        for name, item in after_by_name.items()
        if name in before_by_name
    )
    restart_count_increased = any(
        int(item.get("restarts", 0)) > int(before_by_name[name].get("restarts", 0))
        for name, item in after_by_name.items()
        if name in before_by_name
    )
    before_run_ids = {
        item.get("labels", {}).get("forgeos.io/run-id")
        for item in before.get("pods", [])
        if item.get("labels", {}).get("forgeos.io/run-id")
    }
    after_run_ids = {
        item.get("labels", {}).get("forgeos.io/run-id")
        for item in after.get("pods", [])
        if item.get("labels", {}).get("forgeos.io/run-id")
    }
    stable_identity = bool(before_run_ids) and before_run_ids == after_run_ids
    restart_observed = uid_changed or restart_count_increased
    checks = {
        "lease_expiry": {
            "status": "PASS" if _load_status(lease_evidence, "kubernetes-pod") == "PASS" else "NOT_PROVEN",
            "reason": "requires a runner-produced lease-expiry evidence record",
        },
        "restart_reconciliation": {
            "status": "PASS" if restart_observed and stable_identity else "NOT_PROVEN",
            "reason": (
                "Pod identity changed or restarted while the benchmark run label remained stable"
                if restart_observed and stable_identity
                else "no verified Pod restart with stable run identity was observed"
            ),
        },
        "fail_closed": {
            "status": "PASS" if _load_status(redis_evidence, "redis-capability-probe") == "PASS" else "NOT_PROVEN",
            "reason": "requires a live Redis probe with fail-closed evidence",
        },
    }
    return {
        "schema": "forgeos.recovery_evidence.v1",
        "collected_at": _now(),
        "execution_scope": "kubernetes-cluster-observation",
        "kubernetes_real": True,
        "status": _status(checks),
        "checks": checks,
        "observations": {
            "pod_uid_changed": uid_changed,
            "restart_count_increased": restart_count_increased,
            "run_identity_stable": stable_identity,
        },
        "limitations": [
            "This observer does not restart, delete, or roll back any Kubernetes resource.",
            "PASS requires the runner's lease evidence and the live Redis probe in addition to Pod observations.",
        ],
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local-fixture", "capture", "reconcile"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--namespace", default="forgeos-benchmark")
    parser.add_argument("--selector", default="forgeos.io/benchmark-runner=true")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--lease-evidence", type=Path)
    parser.add_argument("--redis-evidence", type=Path)
    args = parser.parse_args(argv)

    if args.mode == "local-fixture":
        payload = run_local_fixture()
    elif args.mode == "capture":
        payload = capture_kubernetes(args.namespace, args.selector)
    else:
        if args.before is None:
            parser.error("--before is required for reconcile mode")
        try:
            before = json.loads(args.before.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"could not read --before snapshot: {exc}")
        after = capture_kubernetes(args.namespace, args.selector)
        payload = reconcile_kubernetes(
            before,
            after,
            lease_evidence=args.lease_evidence,
            redis_evidence=args.redis_evidence,
        )

    _write(args.output, payload)
    print(json.dumps({"status": payload["status"], "scope": payload["execution_scope"]}, indent=2))
    if payload["status"] == "PASS":
        return 0
    if payload["status"] == "NOT_PROVEN":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
