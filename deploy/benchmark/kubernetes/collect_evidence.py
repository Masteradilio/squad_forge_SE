"""Collect redacted, honest Kubernetes/Helm benchmark evidence.

All cluster operations in this collector are read-only. A missing metrics API,
missing Helm history, or an unobserved failure/rollback is reported as
``NOT_PROVEN`` rather than converted into a successful benchmark claim.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "deploy" / "helm" / "forgeos-cloud"
SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)"
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)")


def redact(value: str) -> str:
    value = URL_CREDENTIAL_PATTERN.sub(r"\1***\3", value)
    return SECRET_PATTERN.sub(r"\1\2***", value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_command(
    command: list[str], *, cwd: Path = ROOT, keep_stdout: bool = False
) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return {
            "command": [redact(part) for part in command],
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": f"executable unavailable: {type(exc).__name__}",
        }
    stdout = redact(result.stdout)
    stderr = redact(result.stderr)
    record: dict[str, Any] = {
        "command": [redact(part) for part in command],
        "exit_code": result.returncode,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }
    if keep_stdout:
        record["_stdout"] = stdout
    return record


def _kubectl_json(*args: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    result = run_command(["kubectl", *args], keep_stdout=True)
    if result["exit_code"] != 0:
        result.pop("_stdout", None)
        return None, result
    try:
        payload = json.loads(result.pop("_stdout", ""))
    except json.JSONDecodeError:
        result["parse_error"] = "kubectl output was not JSON"
        return None, result
    return payload if isinstance(payload, dict) else None, result


def _readiness_claim(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {"status": "NOT_PROVEN", "reason": "deployment state was not available"}
    items = payload.get("items", [])
    if not items:
        return {"status": "NOT_PROVEN", "reason": "no deployment objects were observed"}
    relevant = [
        item
        for item in items
        if item.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/component")
        in {"backend", "frontend", "omniroute"}
    ]
    if not relevant:
        relevant = items
    failures: list[str] = []
    for item in relevant:
        metadata = item.get("metadata", {})
        status = item.get("status", {})
        desired = int(item.get("spec", {}).get("replicas", 0))
        available = int(status.get("availableReplicas", 0))
        ready = int(status.get("readyReplicas", 0))
        if desired != available or desired != ready:
            failures.append(f"{metadata.get('name', 'unknown')}:{ready}/{desired}")
    if failures:
        return {"status": "BLOCKED", "reason": "readiness is not satisfied", "failures": failures}
    return {"status": "PASS", "reason": "observed deployments are ready"}


def _hpa_claim(hpa: dict[str, Any] | None, metrics_api: dict[str, Any] | None) -> dict[str, Any]:
    if hpa is None:
        return {"status": "NOT_PROVEN", "reason": "HPA state was not available"}
    items = hpa.get("items", [])
    if not items:
        return {"status": "NOT_PROVEN", "reason": "no HPA object was observed"}
    if metrics_api is None:
        return {
            "status": "NOT_PROVEN",
            "reason": "metrics.k8s.io is unavailable or returned no JSON; HPA cannot be claimed",
        }
    inactive: list[str] = []
    for item in items:
        name = item.get("metadata", {}).get("name", "unknown")
        conditions = item.get("status", {}).get("conditions", [])
        active = {
            condition.get("type"): condition.get("status")
            for condition in conditions
        }
        if active.get("AbleToScale") != "True" or active.get("ScalingActive") != "True":
            inactive.append(name)
    if inactive:
        return {"status": "NOT_PROVEN", "reason": "HPA conditions are not active", "items": inactive}
    return {"status": "PASS", "reason": "HPA conditions and metrics API are active"}


def _rollback_claim(history: dict[str, Any] | None) -> dict[str, Any]:
    if history is None:
        return {"status": "NOT_PROVEN", "reason": "Helm history was not available"}
    entries = history.get("history", history.get("items", []))
    if not isinstance(entries, list):
        return {"status": "NOT_PROVEN", "reason": "Helm history format was not recognized"}
    verified = [
        item
        for item in entries
        if "rollback" in str(item.get("description", "")).lower()
        and str(item.get("status", "")).lower() == "deployed"
    ]
    if verified:
        return {"status": "PASS", "reason": "Helm history contains a deployed rollback revision"}
    return {
        "status": "NOT_PROVEN",
        "reason": "Helm history has no verified rollback revision; no rollback claim is made",
    }


def _render_contract(chart: Path, release: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if shutil.which("helm") is None:
        return (
            {"status": "NOT_PROVEN", "reason": "helm executable is not installed"},
            {"command": ["helm", "template", release, str(chart)], "exit_code": None},
        )
    command = [
        "helm",
        "template",
        release,
        str(chart),
        "--set",
        "backend.probes.readiness.path=/__forgeos_readiness_failure__",
    ]
    result = run_command(command, keep_stdout=True)
    rendered = result.pop("_stdout", "")
    required = (
        "kind: ConfigMap",
        "deployment-evidence",
        "/__forgeos_readiness_failure__",
        "helm rollback",
        "/var/lib/forgeos/evidence",
    )
    missing = [marker for marker in required if marker not in rendered]
    if result["exit_code"] != 0:
        return {"status": "BLOCKED", "reason": "helm template failed"}, result
    if missing:
        return {"status": "BLOCKED", "reason": "chart evidence contract is incomplete", "missing": missing}, result
    return {"status": "PASS", "reason": "readiness failure and rollback evidence path rendered"}, result


def collect(
    *,
    release: str,
    namespace: str,
    chart: Path,
    output: Path,
) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []
    context = run_command(["kubectl", "config", "current-context"])
    commands.append(context)
    deployments, deployment_command = _kubectl_json("get", "deployments", "-n", namespace, "-o", "json")
    commands.append(deployment_command)
    hpa, hpa_command = _kubectl_json("get", "hpa", "-n", namespace, "-o", "json")
    commands.append(hpa_command)
    metrics, metrics_command = _kubectl_json("get", "--raw", "/apis/metrics.k8s.io/v1beta1")
    commands.append(metrics_command)

    status_command = run_command(
        ["helm", "status", release, "-n", namespace, "-o", "json"], keep_stdout=True
    )
    history_command = run_command(
        ["helm", "history", release, "-n", namespace, "-o", "json"], keep_stdout=True
    )
    commands.extend((status_command, history_command))
    status_payload = None
    history_payload = None
    if status_command["exit_code"] == 0:
        try:
            status_payload = json.loads(status_command.get("_stdout", ""))
        except json.JSONDecodeError:
            pass
    if history_command["exit_code"] == 0:
        try:
            history_payload = json.loads(history_command.get("_stdout", ""))
        except json.JSONDecodeError:
            pass

    chart_claim, render_command = _render_contract(chart, release)
    commands.append(render_command)
    status_command.pop("_stdout", None)
    history_command.pop("_stdout", None)
    # A missing metrics.k8s.io endpoint is an explicit NOT_PROVEN HPA result,
    # not a failure of the read-only cluster observation itself.
    kubectl_failed = any(item["exit_code"] != 0 for item in commands[:3])
    claims = {
        "readiness": _readiness_claim(deployments),
        "readiness_failure_rollback_path": chart_claim,
        "rollback": _rollback_claim(history_payload),
        "hpa": _hpa_claim(hpa, metrics),
        "release": {
            "status": "PASS" if status_payload else "NOT_PROVEN",
            "reason": "Helm release status was observed" if status_payload else "Helm release status was not observed",
        },
    }
    statuses = {item["status"] for item in claims.values()}
    if kubectl_failed or "BLOCKED" in statuses:
        overall = "BLOCKED"
    elif statuses == {"PASS"}:
        overall = "PASS"
    else:
        overall = "NOT_PROVEN"
    return {
        "schema": "forgeos.kubernetes_benchmark_evidence.v1",
        "collected_at": _now(),
        "execution_scope": "kubernetes-cluster-observation",
        "kubernetes_real": not kubectl_failed,
        "release": release,
        "namespace": namespace,
        "status": overall,
        "claims": claims,
        "commands": commands,
        "limitations": [
            "Readiness failure and rollback are NOT_PROVEN until a controlled rollout and Helm rollback are observed.",
            "HPA is NOT_PROVEN when metrics.k8s.io/metrics-server is absent; use the recorded diagnostic command.",
            "No Secret object or Secret value was queried or persisted.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="forgeos")
    parser.add_argument("--namespace", default="forgeos")
    parser.add_argument("--chart", type=Path, default=CHART)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "deploy" / "benchmark" / "kubernetes" / "evidence.json",
    )
    args = parser.parse_args(argv)
    evidence = collect(
        release=args.release,
        namespace=args.namespace,
        chart=args.chart.resolve(),
        output=args.output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "scope": evidence["execution_scope"]}, indent=2))
    if evidence["status"] == "PASS":
        return 0
    if evidence["status"] == "NOT_PROVEN":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
