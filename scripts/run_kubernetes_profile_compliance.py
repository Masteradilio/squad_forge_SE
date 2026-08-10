"""Prove the generated ForgeOS benchmark profile in a temporary Kubernetes namespace.

The command is verification-only unless ``--apply`` is supplied.  It never reads
Secret objects and only persists redacted command output.  A successful result
requires an observed completed Job and a succeeded runner Pod; a syntactically
valid manifest is not enough to produce PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - python-dotenv is a declared project dependency
    dotenv_values = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_benchmark_k8s_profile import (  # noqa: E402
    DEFAULT_DNS_SERVICE_IP,
    DEFAULT_SERVICE_NAMES,
    DEFAULT_TARGET_NAMESPACE,
    DNS_EGRESS_PORTS,
    DNS_NAMESPACE_SELECTOR,
    PIDS_LIMIT,
    PIDS_LIMIT_ANNOTATION,
    build_profile,
    normalize_run_id,
    service_fqdn,
    validate_profile,
    write_outputs,
)


SCHEMA = "forgeos.kubernetes_benchmark_profile_compliance.v1"
DEFAULT_RUNNER_IMAGE = "localforge/forgeos-benchmark-runner:dev"
DEFAULT_CONTEXT = "docker-desktop"
DEFAULT_WAIT_SECONDS = 900
DEFAULT_POLL_SECONDS = 5
REDACTED = "[REDACTED]"
SECRET_KEY_NAMES = {
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
}
SECRET_NAME_PATTERN = re.compile(
    r"(?i)\b(?:[a-z0-9_]*(?:password|token|secret|api[_-]?key)|authorization)\b"
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)")
BEARER_PATTERN = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:[a-z0-9_]*(?:password|token|secret|api[_-]?key)|authorization)\b\s*[:=]\s*)([\"']?)[^\s,;\"']+"
)
IMAGE_FAILURE_REASONS = {
    "containercannotrun",
    "createcontainerconfigerror",
    "errimageneverpull",
    "errimagepull",
    "imagepullbackoff",
    "invalidimagename",
}
RUNTIME_SECRET_KEYS = (
    "CONTEXT7_API_KEY",
    "OMNIROUTE_API_KEY",
    "LOCALFORGE_API_TOKEN",
    "REDIS_PASSWORD",
    "POSTGRES_PASSWORD",
)


@dataclass(frozen=True)
class KubectlResult:
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized != "runtime_secret" and (normalized in SECRET_KEY_NAMES or normalized.endswith(
        ("_password", "_token", "_secret", "_api_key", "_apikey", "_authorization")
    ))


def redact_text(value: str) -> str:
    """Redact credential-shaped values without exposing command output."""

    redacted = URL_CREDENTIAL_PATTERN.sub(r"\1" + REDACTED + r"\3", value)
    redacted = BEARER_PATTERN.sub(r"\1" + REDACTED, redacted)
    redacted = ASSIGNMENT_PATTERN.sub(r"\1" + REDACTED, redacted)
    return redacted


def redact_job_logs(value: str) -> str:
    """Keep useful non-secret log lines while suppressing sensitive lines."""

    lines: list[str] = []
    for line in value.splitlines():
        if SECRET_NAME_PATTERN.search(line) or re.search(r"(?i)authorization\s*:", line):
            lines.append(REDACTED + " sensitive log line")
        else:
            lines.append(redact_text(line))
    return "\n".join(lines) + ("\n" if value.endswith(("\n", "\r")) else "")


def redact_json_payload(value: Any, *, parent_kind: str | None = None, parent_key: str | None = None) -> Any:
    """Redact values in structured output before it can become an artifact."""

    if isinstance(value, dict):
        kind = str(value.get("kind", parent_kind or ""))
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if kind == "Secret" or (parent_kind == "Secret" and key_text in {"data", "stringData"}):
                result[key_text] = REDACTED
            elif key_text == "secretKeyRef":
                # This is a reference, not a Secret value.  Keep the reference
                # so the evidence proves that credentials are injected at runtime.
                result[key_text] = redact_json_payload(item, parent_kind=kind, parent_key=key_text)
            elif _is_secret_key(key_text):
                result[key_text] = REDACTED
            else:
                result[key_text] = redact_json_payload(item, parent_kind=kind, parent_key=key_text)
        return result
    if isinstance(value, list):
        return [redact_json_payload(item, parent_kind=parent_kind, parent_key=parent_key) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _redact_command(command: Sequence[str]) -> list[str]:
    return [redact_text(str(part)) for part in command]


def _kubectl_command(kubectl: str, context: str | None, args: Sequence[str]) -> list[str]:
    command = [kubectl]
    if context:
        command.extend(("--context", context))
    command.extend(str(arg) for arg in args)
    return command


def run_kubectl(
    kubectl: str,
    args: Sequence[str],
    *,
    context: str | None = DEFAULT_CONTEXT,
    timeout_seconds: float = 60,
    json_output: bool = False,
    input_text: str | None = None,
) -> KubectlResult:
    """Run one kubectl command and return output that is already redacted."""

    command = _kubectl_command(kubectl, context, args)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=input_text,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return KubectlResult(tuple(_redact_command(command)), None, "", "kubectl executable is unavailable")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return KubectlResult(
            tuple(_redact_command(command)),
            None,
            redact_text(stdout),
            redact_text(stderr) + " command timed out",
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if json_output and stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            safe_stdout = redact_text(stdout)
        else:
            safe_stdout = json.dumps(redact_json_payload(payload), ensure_ascii=False)
    else:
        safe_stdout = redact_text(stdout)
    return KubectlResult(
        tuple(_redact_command(command)),
        completed.returncode,
        safe_stdout,
        redact_text(stderr),
    )


def _result_record(result: KubectlResult, *, include_stdout: bool = True) -> dict[str, Any]:
    record: dict[str, Any] = {
        "command": list(result.command),
        "exit_code": result.exit_code,
        "stderr_tail": result.stderr[-2000:],
    }
    if include_stdout:
        record["stdout_tail"] = result.stdout[-2000:]
    return record


def _parse_json_result(result: KubectlResult) -> dict[str, Any] | None:
    if not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = redact_json_payload(payload)
    path.write_text(json.dumps(safe_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_result_json(path: Path, result: KubectlResult, payload: dict[str, Any] | None = None) -> None:
    if payload is not None:
        _write_json(path, payload)
        return
    _write_json(path, {"observed": False, "command": list(result.command), **_result_record(result)})


def _write_result_text(path: Path, result: KubectlResult, *, logs: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stdout = redact_job_logs(result.stdout) if logs else redact_text(result.stdout)
    stderr = redact_text(result.stderr)
    content = stdout
    if stderr:
        content += ("\n" if content and not content.endswith("\n") else "") + "stderr:\n" + stderr
    if not content:
        content = "No output observed.\n"
    path.write_text(content, encoding="utf-8")


def _write_manifest_documents(path: Path, manifests: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n".join(yaml.safe_dump(item, sort_keys=False) for item in manifests),
        encoding="utf-8",
    )


def _write_apply_phase_manifests(profile: dict[str, Any], evidence_dir: Path) -> dict[str, str]:
    manifests = profile["manifests"]
    bootstrap_path = evidence_dir / "profile-without-job.yaml"
    job_path = evidence_dir / "job-manifest.yaml"
    _write_manifest_documents(bootstrap_path, [item for item in manifests if item.get("kind") != "Job"])
    _write_manifest_documents(job_path, [item for item in manifests if item.get("kind") == "Job"])
    return {
        "bootstrap_profile": _artifact_ref(bootstrap_path, evidence_dir.parent),
        "job_manifest": _artifact_ref(job_path, evidence_dir.parent),
    }


def _workspace_env_values() -> dict[str, str]:
    """Read only approved runtime keys from the workspace root .env, without mutating os.environ."""
    if dotenv_values is None:
        return {}
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return {}
    try:
        parsed_values = dotenv_values(env_path)
    except (OSError, UnicodeError, ValueError):
        return {}
    return {
        key: value
        for key, value in parsed_values.items()
        if key in RUNTIME_SECRET_KEYS and isinstance(value, str)
    }


def _runtime_secret_payloads(
    *,
    namespace: str,
    run_id: str,
    context7_secret_name: str,
    omniroute_secret_name: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    workspace_values = _workspace_env_values()
    for key in RUNTIME_SECRET_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
            sources[key] = "caller-environment"
        elif key in workspace_values:
            values[key] = workspace_values[key]
            sources[key] = "workspace-dotenv"
        else:
            values[key] = f"forgeos-compliance-dummy-{key.lower().replace('_', '-')}"
            sources[key] = "deterministic-dummy"

    key_groups: dict[str, list[str]] = {}
    for key in RUNTIME_SECRET_KEYS:
        secret_name = context7_secret_name if key == "CONTEXT7_API_KEY" else omniroute_secret_name
        key_groups.setdefault(secret_name, []).append(key)
    payloads = [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": secret_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/part-of": "forgeos-benchmark",
                    "forgeos.io/run-id": run_id,
                },
            },
            "type": "Opaque",
            "stringData": {key: values[key] for key in keys},
        }
        for secret_name, keys in key_groups.items()
    ]
    return payloads, sources


def _bootstrap_runtime_secret(
    kubectl: str,
    context: str | None,
    namespace: str,
    run_id: str,
    context7_secret_name: str,
    omniroute_secret_name: str,
    evidence_dir: Path,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create only temporary runtime Secret objects, keeping values off disk."""

    payloads, sources = _runtime_secret_payloads(
        namespace=namespace,
        run_id=run_id,
        context7_secret_name=context7_secret_name,
        omniroute_secret_name=omniroute_secret_name,
    )
    results: list[dict[str, Any]] = []
    for payload in payloads:
        result = run_kubectl(
            kubectl,
            ["apply", "-f", "-", "-o", "name"],
            context=context,
            timeout_seconds=60,
            input_text=json.dumps(payload, ensure_ascii=False),
        )
        _record_command(commands, result, include_stdout=False)
        results.append(
            {
                "name": payload["metadata"]["name"],
                "keys": sorted(payload["stringData"]),
                "status": "PASS" if result.ok else "BLOCKED",
                "exit_code": result.exit_code,
                "stderr": result.stderr[-1000:],
            }
        )
    status = "PASS" if results and all(item["status"] == "PASS" for item in results) else "BLOCKED"
    summary = {
        "status": status,
        "secret_names": [item["name"] for item in results],
        "keys": sorted(RUNTIME_SECRET_KEYS),
        "value_sources": [{"key": key, "source": sources[key]} for key in RUNTIME_SECRET_KEYS],
        "values_persisted": False,
        "reason": "temporary Secret objects applied from stdin; values were not written to artifacts"
        if status == "PASS"
        else "one or more temporary runtime Secret objects could not be applied",
    }
    _write_json(evidence_dir / "runtime-secret.json", {**summary, "results": results})
    return summary


def _artifact_ref(path: Path, artifact_root: Path) -> str:
    return path.relative_to(artifact_root).as_posix()


def _record_command(commands: list[dict[str, Any]], result: KubectlResult, *, include_stdout: bool = True) -> None:
    commands.append(_result_record(result, include_stdout=include_stdout))


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def validate_profile_for_compliance(profile: dict[str, Any]) -> dict[str, Any]:
    """Run the generated validator plus the live-proof-specific safety checks."""

    validate_profile(profile)
    manifests = profile["manifests"]
    jobs = [item for item in manifests if item.get("kind") == "Job"]
    job = jobs[0]
    pod_spec = job["spec"]["template"]["spec"]
    containers = pod_spec.get("containers") or []
    checks: dict[str, dict[str, Any]] = {}

    forbidden: list[str] = []
    for manifest in manifests:
        for item in _iter_dicts(manifest):
            for key, value in item.items():
                key_lower = str(key).lower()
                if key_lower == "hostpath":
                    forbidden.append("hostPath")
                elif key_lower in {"hostnetwork", "hostpid", "hostipc", "privileged"} and value is True:
                    forbidden.append(key)
    checks["no_hostpath_or_host_namespace_access"] = {
        "status": "PASS" if not forbidden else "BLOCKED",
        "reason": "no hostPath/host namespace/privileged fields" if not forbidden else f"forbidden fields: {sorted(set(forbidden))}",
    }

    limits = containers[0].get("resources", {}).get("limits", {}) if containers else {}
    job_annotations = job.get("metadata", {}).get("annotations", {})
    template_annotations = job.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {})
    pids_limit = profile.get("resource_bounds", {}).get("pids_limit")
    pids_evidence_ok = (
        pids_limit == PIDS_LIMIT
        and profile.get("runner", {}).get("pids_limit") == PIDS_LIMIT
        and job_annotations.get(PIDS_LIMIT_ANNOTATION) == str(PIDS_LIMIT)
        and template_annotations.get(PIDS_LIMIT_ANNOTATION) == str(PIDS_LIMIT)
        and "pids" not in limits
    )
    checks["pids_limit_metadata"] = {
        "status": "PASS" if pids_evidence_ok else "BLOCKED",
        "limit": pids_limit,
        "annotation": PIDS_LIMIT_ANNOTATION,
        "reason": "pids limit is recorded as explicit Job/Pod metadata; no invalid container resource is emitted"
        if pids_evidence_ok
        else "pids limit metadata is missing or an invalid container pids resource is present",
    }

    namespace = profile["namespace"]
    namespace_manifests = [item for item in manifests if item.get("kind") == "Namespace"]
    namespace_labels = namespace_manifests[0].get("metadata", {}).get("labels", {}) if namespace_manifests else {}
    identity_ok = (
        len(namespace_manifests) == 1
        and namespace_manifests[0].get("metadata", {}).get("name") == namespace
        and namespace_labels.get("app.kubernetes.io/part-of") == "forgeos-benchmark"
        and namespace_labels.get("forgeos.io/run-id") == profile["run_id"]
    )
    checks["namespace_identity"] = {
        "status": "PASS" if identity_ok else "BLOCKED",
        "reason": "generated namespace name and ownership labels are exact" if identity_ok else "generated namespace identity or ownership labels are invalid",
    }

    pod_security = pod_spec.get("securityContext", {})
    run_as_user = pod_security.get("runAsUser")
    run_as_group = pod_security.get("runAsGroup")
    unprivileged = (
        pod_security.get("runAsNonRoot") is True
        and isinstance(run_as_user, int)
        and run_as_user > 0
        and isinstance(run_as_group, int)
        and run_as_group > 0
        and pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault"
        and bool(containers)
        and all(
            container.get("securityContext", {}).get("allowPrivilegeEscalation") is False
            and container.get("securityContext", {}).get("capabilities", {}).get("drop")
            and "ALL" in container["securityContext"]["capabilities"]["drop"]
            for container in containers
        )
    )
    checks["unprivileged"] = {
        "status": "PASS" if unprivileged else "BLOCKED",
        "reason": "Pod and runner container security contexts are unprivileged" if unprivileged else "unprivileged security context is incomplete",
    }

    read_only = bool(containers) and all(
        container.get("securityContext", {}).get("readOnlyRootFilesystem") is True for container in containers
    )
    checks["read_only_root_filesystem"] = {
        "status": "PASS" if read_only else "BLOCKED",
        "reason": "all runner containers use read-only root filesystems" if read_only else "a runner container can write its root filesystem",
    }

    literal_secret_values = [
        item.get("name", "unknown")
        for container in containers
        for item in container.get("env", [])
        if _is_secret_key(str(item.get("name", ""))) and "valueFrom" not in item
    ]
    secret_kinds = [item.get("kind") for item in manifests if item.get("kind") == "Secret"]
    has_string_data = any("stringData" in item for item in _iter_dicts(manifests))
    secret_safe = not literal_secret_values and not secret_kinds and not has_string_data
    checks["no_secret_values"] = {
        "status": "PASS" if secret_safe else "BLOCKED",
        "reason": "only runtime Secret references are present" if secret_safe else "literal Secret data or values were found",
    }

    command_ok = job.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("command") == ["localforge"]
    command_ok = command_ok and job["spec"]["template"]["spec"]["containers"][0].get("args", [])[:2] == ["benchmark", "report"]
    checks["benchmark_command"] = {
        "status": "PASS" if command_ok else "BLOCKED",
        "reason": "Job invokes localforge benchmark report" if command_ok else "Job command is not the generated benchmark command",
    }

    targets = profile.get("targets", {})
    target_namespace = targets.get("namespace")
    services = targets.get("services", {})
    configmaps = [item for item in manifests if item.get("kind") == "ConfigMap"]
    configmap_data = configmaps[0].get("data", {}) if configmaps else {}
    expected_service_fqdns = {
        key: service_fqdn(value, target_namespace)
        for key, value in services.items()
        if isinstance(value, str) and isinstance(target_namespace, str)
    }
    expected_service_config = {
        "FORGEOS_BACKEND_URL": f"http://{expected_service_fqdns.get('backend')}:8000",
        "REDIS_HOST": expected_service_fqdns.get("redis"),
        "POSTGRES_HOST": expected_service_fqdns.get("postgres"),
        "OMNIROUTE_URL": f"http://{expected_service_fqdns.get('omniroute')}:20128/v1",
    }
    service_fqdn_ok = (
        isinstance(target_namespace, str)
        and targets.get("service_fqdns") == expected_service_fqdns
        and all(configmap_data.get(key) == value for key, value in expected_service_config.items())
    )
    checks["cross_namespace_service_fqdns"] = {
        "status": "PASS" if service_fqdn_ok else "BLOCKED",
        "target_namespace": target_namespace,
        "service_fqdns": expected_service_fqdns,
        "reason": "ConfigMap uses target-namespace service FQDNs for backend, Redis, Postgres, and OmniRoute"
        if service_fqdn_ok
        else "ConfigMap service endpoints must use target-namespace FQDNs under svc.cluster.local",
    }

    network_policies = [item for item in manifests if item.get("kind") == "NetworkPolicy"]
    policy_ok = bool(network_policies) and all(
        item.get("spec", {}).get("policyTypes") and item["spec"].get("ingress") == [] for item in network_policies
    )
    checks["network_policy"] = {
        "status": "PASS" if policy_ok else "BLOCKED",
        "reason": "NetworkPolicy denies ingress for the runner" if policy_ok else "NetworkPolicy ingress isolation is incomplete",
    }

    dns_config = profile.get("resource_bounds", {}).get("dns", {})
    dns_service_ip_block = dns_config.get("ip_block") if isinstance(dns_config, dict) else None
    dns_ports = [dict(item) for item in DNS_EGRESS_PORTS]
    dns_egress = network_policies[0].get("spec", {}).get("egress", []) if network_policies else []
    dns_selector_ok = any(
        item.get("to") == [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": DNS_NAMESPACE_SELECTOR}}}]
        and item.get("ports") == dns_ports
        for item in dns_egress
    )
    dns_ip_block_ok = isinstance(dns_service_ip_block, str) and any(
        item.get("to") == [{"ipBlock": {"cidr": dns_service_ip_block}}]
        and item.get("ports") == dns_ports
        for item in dns_egress
    )
    checks["network_policy_dns"] = {
        "status": "PASS" if dns_selector_ok and dns_ip_block_ok else "BLOCKED",
        "service_ip_block": dns_service_ip_block,
        "namespace_selector": DNS_NAMESPACE_SELECTOR,
        "ports": dns_ports,
        "reason": "DNS egress retains kube-system selector and permits the exact service IP block on TCP/UDP 53"
        if dns_selector_ok and dns_ip_block_ok
        else "DNS egress must retain kube-system selector and permit the exact service IP block on TCP/UDP 53",
    }

    failed = [name for name, check in checks.items() if check["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_checks": failed,
    }


def _namespace_identity(payload: dict[str, Any] | None, *, namespace: str, run_id: str) -> bool:
    if not payload or payload.get("metadata", {}).get("name") != namespace:
        return False
    labels = payload.get("metadata", {}).get("labels", {})
    return (
        labels.get("app.kubernetes.io/part-of") == "forgeos-benchmark"
        and labels.get("forgeos.io/run-id") == run_id
    )


def _not_found(result: KubectlResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return result.exit_code == 1 and any(marker in text for marker in ("notfound", "not found", "could not find"))


def _dry_run_only_lacks_temporary_namespace(result: KubectlResult, namespace: str) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return f'namespaces "{namespace.lower()}" not found' in text and not any(
        marker in text
        for marker in (
            "invalid value",
            "forbidden",
            "denied the request",
            "unknown field",
            "must be a standard resource",
        )
    )


def _find_kubectl(explicit: str | None) -> str | None:
    if explicit:
        resolved = shutil.which(explicit)
        if resolved:
            return resolved
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate)
        return None
    return shutil.which("kubectl") or shutil.which("kubectl.exe")


def _preflight(
    kubectl: str,
    context: str | None,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    context_result = run_kubectl(
        kubectl,
        ["config", "get-contexts", "--no-headers", "-o", "name", context] if context else ["config", "current-context"],
        context=None,
    )
    _record_command(commands, context_result)
    if not context_result.ok or (context and context not in context_result.stdout.split()):
        return {
            "status": "BLOCKED",
            "reason": f"kubectl context is unavailable: {context or 'current context'}",
        }

    version_result = run_kubectl(kubectl, ["version", "--output=json"], context=context)
    _record_command(commands, version_result)
    if not version_result.ok:
        return {"status": "BLOCKED", "reason": "Kubernetes API is unavailable for the selected context"}
    return {
        "status": "PASS",
        "context": context or context_result.stdout.strip(),
        "reason": "kubectl reached the selected Kubernetes API",
    }


def evaluate_job_completion(job: dict[str, Any] | None, pods: dict[str, Any] | None) -> dict[str, Any]:
    """Classify observed Job/Pod state without treating a missing image as success."""

    job_status = (job or {}).get("status", {})
    if not isinstance(job_status, dict):
        job_status = {}
    pod_items = (pods or {}).get("items", [])
    if not isinstance(pod_items, list):
        pod_items = []
    pod_items = [item for item in pod_items if isinstance(item, dict)]
    pod_phases = [item.get("status", {}).get("phase") for item in pod_items]
    waiting_reasons: list[str] = []
    terminated_reasons: list[str] = []
    messages: list[str] = []
    for pod in pod_items:
        status = pod.get("status", {})
        if not isinstance(status, dict):
            status = {}
        container_statuses = status.get("containerStatuses", [])
        if not isinstance(container_statuses, list):
            container_statuses = []
        for container_status in container_statuses:
            if not isinstance(container_status, dict):
                continue
            waiting = container_status.get("state", {}).get("waiting", {})
            terminated = container_status.get("state", {}).get("terminated", {})
            if waiting.get("reason"):
                waiting_reasons.append(str(waiting["reason"]))
            if terminated.get("reason"):
                terminated_reasons.append(str(terminated["reason"]))
            if waiting.get("message"):
                messages.append(str(waiting["message"]))
            if terminated.get("message"):
                messages.append(str(terminated["message"]))

    failure_text = " ".join((*waiting_reasons, *terminated_reasons, *messages)).lower().replace(" ", "")
    image_failure = any(reason.lower().replace(" ", "") in IMAGE_FAILURE_REASONS for reason in (*waiting_reasons, *terminated_reasons))
    image_failure = image_failure or any(
        marker in failure_text for marker in ("imagepull", "imageneverpull", "executablefilenotfound", "notfound", "createcontainerconfigerror")
    )
    conditions = job_status.get("conditions", [])
    if not isinstance(conditions, list):
        conditions = []
    complete = any(
        condition.get("type") == "Complete" and condition.get("status") == "True"
        for condition in conditions
        if isinstance(condition, dict)
    )
    succeeded_pod = "Succeeded" in pod_phases
    try:
        succeeded_count = int(job_status.get("succeeded", 0) or 0)
    except (TypeError, ValueError):
        succeeded_count = 0
    job_failure_reasons = sorted(
        {
            str(condition.get("reason"))
            for condition in conditions
            if isinstance(condition, dict) and condition.get("type") in {"Failed", "FailureTarget"} and condition.get("reason")
        }
    )
    if complete and succeeded_count > 0 and succeeded_pod:
        return {
            "status": "PASS",
            "reason": "Job Complete and a runner Pod reached Succeeded",
            "job_complete": True,
            "pod_succeeded": True,
            "pod_phases": pod_phases,
        }
    if image_failure:
        return {
            "status": "BLOCKED",
            "reason": "runner image or command could not start; completion was not proven",
            "job_complete": complete,
            "pod_succeeded": succeeded_pod,
            "pod_phases": pod_phases,
            "failure_reasons": sorted(set((*waiting_reasons, *terminated_reasons))),
            "job_failure_reasons": job_failure_reasons,
        }
    if any(
        condition.get("type") == "Failed" and condition.get("status") == "True"
        for condition in conditions
        if isinstance(condition, dict)
    ):
        return {
            "status": "BLOCKED",
            "reason": "Job entered Failed"
            + (f" ({', '.join(job_failure_reasons)})" if job_failure_reasons else "")
            + "; completion was not proven",
            "job_complete": complete,
            "pod_succeeded": succeeded_pod,
            "pod_phases": pod_phases,
            "job_failure_reasons": job_failure_reasons,
        }
    return {
        "status": "NOT_PROVEN",
        "reason": "Job/Pod has not reached an observed successful terminal state",
        "job_complete": complete,
        "pod_succeeded": succeeded_pod,
        "pod_phases": pod_phases,
    }


def _wait_for_job(
    kubectl: str,
    context: str | None,
    namespace: str,
    commands: list[dict[str, Any]],
    *,
    wait_seconds: int,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, wait_seconds)
    last_job: dict[str, Any] | None = None
    last_pods: dict[str, Any] | None = None
    attempts = 0
    while True:
        attempts += 1
        job_result = run_kubectl(
            kubectl,
            ["get", "job", "forgeos-benchmark-runner", "-n", namespace, "-o", "json"],
            context=context,
            json_output=True,
        )
        pod_result = run_kubectl(
            kubectl,
            ["get", "pods", "-n", namespace, "-l", "job-name=forgeos-benchmark-runner", "-o", "json"],
            context=context,
            json_output=True,
        )
        _record_command(commands, job_result)
        _record_command(commands, pod_result)
        last_job = _parse_json_result(job_result)
        last_pods = _parse_json_result(pod_result)
        state = evaluate_job_completion(last_job, last_pods)
        state["attempts"] = attempts
        if state["status"] in {"PASS", "BLOCKED"}:
            return state
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            state["status"] = "NOT_PROVEN"
            state["reason"] = f"Job did not complete within {wait_seconds} seconds"
            return state
        if poll_seconds > 0:
            time.sleep(min(poll_seconds, remaining))


def _capture_evidence(
    kubectl: str,
    context: str | None,
    namespace: str,
    evidence_dir: Path,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    resources = {
        "namespace.json": (["get", "namespace", namespace, "-o", "json"], None),
        "serviceaccount.json": (["get", "serviceaccount", "forgeos-benchmark-runner", "-n", namespace, "-o", "json"], None),
        "role.json": (["get", "role", "forgeos-benchmark-runner", "-n", namespace, "-o", "json"], None),
        "rolebinding.json": (["get", "rolebinding", "forgeos-benchmark-runner", "-n", namespace, "-o", "json"], None),
        "configmap.json": (["get", "configmap", "forgeos-benchmark-config", "-n", namespace, "-o", "json"], None),
        "resourcequota.json": (["get", "resourcequota", "forgeos-benchmark-quota", "-n", namespace, "-o", "json"], None),
        "pvc.json": (["get", "pvc", "forgeos-benchmark-state", "-n", namespace, "-o", "json"], None),
        "networkpolicy.json": (["get", "networkpolicy", "forgeos-benchmark-default-deny", "-n", namespace, "-o", "json"], None),
        "job.json": (["get", "job", "forgeos-benchmark-runner", "-n", namespace, "-o", "json"], None),
        "pods.json": (["get", "pods", "-n", namespace, "-l", "job-name=forgeos-benchmark-runner", "-o", "json"], None),
        "events.json": (["get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "-o", "json"], None),
    }
    paths: dict[str, str] = {}
    payloads: dict[str, dict[str, Any] | None] = {}
    for filename, (args, _) in resources.items():
        result = run_kubectl(kubectl, args, context=context, json_output=True)
        _record_command(commands, result)
        payload = _parse_json_result(result)
        _write_result_json(evidence_dir / filename, result, payload)
        paths[filename.removesuffix(".json")] = _artifact_ref(evidence_dir / filename, evidence_dir.parent)
        payloads[filename] = payload

    describe_commands = {
        "describe-namespace.txt": ["describe", "namespace", namespace],
        "describe-rbac.txt": [
            "describe",
            "serviceaccount,role,rolebinding",
            "forgeos-benchmark-runner",
            "-n",
            namespace,
        ],
        "describe-networkpolicy.txt": ["describe", "networkpolicy", "forgeos-benchmark-default-deny", "-n", namespace],
        "describe-job.txt": ["describe", "job", "forgeos-benchmark-runner", "-n", namespace],
        "describe-pods.txt": ["describe", "pods", "-n", namespace, "-l", "job-name=forgeos-benchmark-runner"],
    }
    for filename, args in describe_commands.items():
        result = run_kubectl(kubectl, args, context=context)
        _record_command(commands, result)
        _write_result_text(evidence_dir / filename, result)
        paths[filename.removesuffix(".txt")] = _artifact_ref(evidence_dir / filename, evidence_dir.parent)

    service_account = f"system:serviceaccount:{namespace}:forgeos-benchmark-runner"
    rbac_checks = (
        ("get-pods", "get", "pods", True),
        ("list-pods", "list", "pods", True),
        ("watch-pods", "watch", "pods", True),
        ("get-pod-logs", "get", "pods/log", True),
        ("get-events", "get", "events", True),
        ("get-services", "get", "services", True),
        ("get-configmaps", "get", "configmaps", True),
        ("get-deployments", "get", "deployments.apps", True),
        ("get-statefulsets", "get", "statefulsets.apps", True),
        ("get-jobs", "get", "jobs.batch", True),
        ("create-pods", "create", "pods", False),
        ("delete-pods", "delete", "pods", False),
        ("get-secrets", "get", "secrets", False),
        ("list-secrets", "list", "secrets", False),
        ("create-jobs", "create", "jobs.batch", False),
        ("delete-jobs", "delete", "jobs.batch", False),
    )
    rbac_results: list[dict[str, Any]] = []
    for name, verb, resource, expected in rbac_checks:
        result = run_kubectl(
            kubectl,
            ["auth", "can-i", verb, resource, "--as", service_account, "--namespace", namespace],
            context=context,
        )
        _record_command(commands, result)
        observed = result.stdout.strip().lower()
        rbac_results.append(
            {
                "name": name,
                "verb": verb,
                "resource": resource,
                "expected": "yes" if expected else "no",
                "observed": observed or None,
                "status": "PASS"
                if result.exit_code == (0 if expected else 1) and observed == ("yes" if expected else "no")
                else "NOT_PROVEN",
            }
        )
    _write_json(evidence_dir / "rbac-can-i.json", {"service_account": service_account, "checks": rbac_results})
    paths["rbac-can-i"] = _artifact_ref(evidence_dir / "rbac-can-i.json", evidence_dir.parent)

    logs_result = run_kubectl(
        kubectl,
        [
            "logs",
            "job/forgeos-benchmark-runner",
            "-n",
            namespace,
            "--all-containers=true",
            "--timestamps=true",
            "--tail=2000",
        ],
        context=context,
        timeout_seconds=60,
    )
    _record_command(commands, logs_result, include_stdout=False)
    _write_result_text(evidence_dir / "job.log", logs_result, logs=True)
    paths["job-log"] = _artifact_ref(evidence_dir / "job.log", evidence_dir.parent)

    return {
        "paths": paths,
        "job": payloads.get("job.json"),
        "pods": payloads.get("pods.json"),
        "rbac": rbac_results,
    }


def _cleanup_namespace(
    kubectl: str,
    context: str | None,
    namespace: str,
    run_id: str,
    evidence_dir: Path,
    commands: list[dict[str, Any]],
    *,
    apply_started: bool,
    keep_namespace: bool,
) -> dict[str, Any]:
    if not apply_started:
        return {"status": "NOT_PROVEN", "reason": "no namespace mutation was started"}
    if keep_namespace:
        return {"status": "NOT_PROVEN", "reason": "namespace retained by --keep-namespace"}

    identity_result = run_kubectl(kubectl, ["get", "namespace", namespace, "-o", "json"], context=context, json_output=True)
    _record_command(commands, identity_result)
    identity_payload = _parse_json_result(identity_result)
    _write_result_json(evidence_dir / "cleanup-namespace-before-delete.json", identity_result, identity_payload)
    if not _namespace_identity(identity_payload, namespace=namespace, run_id=run_id):
        return {
            "status": "BLOCKED",
            "reason": "refused cleanup because namespace identity or labels were not verified",
        }

    delete_result = run_kubectl(
        kubectl,
        ["delete", "namespace", namespace, "--wait=true"],
        context=context,
        timeout_seconds=180,
    )
    _record_command(commands, delete_result)
    _write_result_text(evidence_dir / "cleanup-delete.txt", delete_result)
    if not delete_result.ok:
        return {"status": "BLOCKED", "reason": "namespace deletion failed after identity verification"}

    verify_result = run_kubectl(
        kubectl,
        ["get", "namespace", namespace, "--ignore-not-found", "-o", "name"],
        context=context,
    )
    _record_command(commands, verify_result)
    _write_result_text(evidence_dir / "cleanup-verify.txt", verify_result)
    if verify_result.ok and not verify_result.stdout.strip():
        return {"status": "PASS", "reason": "exact generated namespace was deleted and absence was verified"}
    return {"status": "BLOCKED", "reason": "namespace deletion was not verified"}


def _status_code(status: str) -> int:
    return {"PASS": 0, "BLOCKED": 2, "NOT_PROVEN": 3}.get(status, 2)


def run_compliance(
    *,
    run_id: str,
    output_dir: Path,
    runner_image: str = DEFAULT_RUNNER_IMAGE,
    apply: bool = False,
    keep_namespace: bool = False,
    bootstrap_runtime_secret: bool = False,
    context: str | None = DEFAULT_CONTEXT,
    kubectl_path: str | None = None,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    project_id: int = 1,
    target_namespace: str = DEFAULT_TARGET_NAMESPACE,
    context7_secret_name: str = "forgeos-runtime-secrets",
    omniroute_secret_name: str = "forgeos-runtime-secrets",
    backend_service_name: str = DEFAULT_SERVICE_NAMES["backend"],
    redis_service_name: str = DEFAULT_SERVICE_NAMES["redis"],
    postgres_service_name: str = DEFAULT_SERVICE_NAMES["postgres"],
    omniroute_service_name: str = DEFAULT_SERVICE_NAMES["omniroute"],
    dns_service_ip: str = DEFAULT_DNS_SERVICE_IP,
) -> dict[str, Any]:
    normalized_run_id = normalize_run_id(run_id)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = output_dir / "evidence"
    report_path = output_dir / "compliance-report.json"
    profile = build_profile(
        normalized_run_id,
        context7_secret_name=context7_secret_name,
        omniroute_secret_name=omniroute_secret_name,
        target_namespace=target_namespace,
        backend_service_name=backend_service_name,
        redis_service_name=redis_service_name,
        postgres_service_name=postgres_service_name,
        omniroute_service_name=omniroute_service_name,
        runner_image=runner_image,
        project_id=project_id,
        dns_service_ip=dns_service_ip,
    )
    write_outputs(output_dir, profile)
    manifest_path = output_dir / "manifest.yaml"
    manifest_hash = sha256_file(manifest_path)
    (output_dir / "manifest.sha256").write_text(manifest_hash + "  manifest.yaml\n", encoding="utf-8")

    profile_validation = validate_profile_for_compliance(profile)
    namespace = profile["namespace"]
    commands: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "collected_at": datetime.now(UTC).isoformat(),
        "status": "NOT_PROVEN",
        "mode": "apply" if apply else "verify",
        "run_id": normalized_run_id,
        "namespace": namespace,
        "context": context,
        "runner_image": redact_text(runner_image),
        "profile": {
            "status": profile_validation["status"],
            "profile_json": "profile.json",
            "manifest": "manifest.yaml",
            "manifest_sha256": manifest_hash,
            "manifest_sha256_file": "manifest.sha256",
            "checks": profile_validation["checks"],
        },
        "evidence": {},
        "commands": commands,
        "runtime_secret": {
            "status": "REQUESTED" if bootstrap_runtime_secret else "NOT_REQUESTED",
            "values_persisted": False,
        },
        "blockers": [],
        "limitations": [
            "No Secret object is queried and no Secret value is written to evidence.",
            "PASS requires observed Job Complete and a runner Pod in Succeeded phase.",
        ],
    }

    if profile_validation["status"] != "PASS":
        report["status"] = "BLOCKED"
        report["blockers"].append("generated profile failed compliance validation")
        _write_json(report_path, report)
        return report

    if bootstrap_runtime_secret and not apply:
        report["status"] = "BLOCKED"
        report["blockers"].append("--bootstrap-runtime-secret requires explicit --apply")
        _write_json(report_path, report)
        return report

    kubectl = _find_kubectl(kubectl_path)
    if not kubectl:
        report["status"] = "BLOCKED"
        report["blockers"].append("kubectl executable is unavailable")
        _write_json(report_path, report)
        return report

    preflight = _preflight(kubectl, context, commands)
    report["preflight"] = preflight
    if preflight["status"] != "PASS":
        report["status"] = "BLOCKED"
        report["blockers"].append(preflight["reason"])
        _write_json(report_path, report)
        return report

    if not apply:
        dry_run = run_kubectl(
            kubectl,
            ["apply", "--dry-run=server", "-f", str(manifest_path), "-o", "name"],
            context=context,
        )
        _record_command(commands, dry_run)
        _write_result_text(evidence_dir / "server-dry-run.txt", dry_run)
        report["evidence"] = {"server_dry_run": "evidence/server-dry-run.txt"}
        if not dry_run.ok:
            if _dry_run_only_lacks_temporary_namespace(dry_run, namespace):
                report["status"] = "NOT_PROVEN"
                report["blockers"].append(
                    "server-side dry-run cannot validate namespaced objects before the temporary namespace exists; no mutation was performed"
                )
            else:
                report["status"] = "BLOCKED"
                report["blockers"].append("server-side manifest validation failed")
        else:
            report["status"] = "NOT_PROVEN"
            report["blockers"].append("verification-only mode does not create a Pod; rerun with --apply")
        _write_json(report_path, report)
        return report

    existing_result = run_kubectl(kubectl, ["get", "namespace", namespace, "-o", "json"], context=context, json_output=True)
    _record_command(commands, existing_result)
    _write_result_json(evidence_dir / "preexisting-namespace.json", existing_result, _parse_json_result(existing_result))
    if existing_result.ok:
        report["status"] = "BLOCKED"
        report["blockers"].append("generated namespace already exists; refusing to mutate it")
        _write_json(report_path, report)
        return report
    if not _not_found(existing_result):
        report["status"] = "BLOCKED"
        report["blockers"].append("could not prove that generated namespace is absent")
        _write_json(report_path, report)
        return report

    apply_started = True
    phase_evidence: dict[str, str] = {}

    def finish_apply_failure(reason: str) -> dict[str, Any]:
        report["status"] = "BLOCKED"
        report["blockers"].append(reason)
        evidence = _capture_evidence(kubectl, context, namespace, evidence_dir, commands)
        report["evidence"] = {**phase_evidence, **evidence["paths"]}
        report["execution"] = {"status": "BLOCKED", "reason": reason}
        report["cleanup"] = _cleanup_namespace(
            kubectl,
            context,
            namespace,
            normalized_run_id,
            evidence_dir,
            commands,
            apply_started=apply_started,
            keep_namespace=keep_namespace,
        )
        _write_json(report_path, report)
        return report

    if bootstrap_runtime_secret:
        phase_evidence = _write_apply_phase_manifests(profile, evidence_dir)
        bootstrap_profile_result = run_kubectl(
            kubectl,
            ["apply", "-f", str(evidence_dir / "profile-without-job.yaml"), "-o", "name"],
            context=context,
            timeout_seconds=120,
        )
        _record_command(commands, bootstrap_profile_result)
        _write_result_text(evidence_dir / "apply-bootstrap.txt", bootstrap_profile_result)
        phase_evidence["apply-bootstrap"] = _artifact_ref(evidence_dir / "apply-bootstrap.txt", evidence_dir.parent)
        if not bootstrap_profile_result.ok:
            return finish_apply_failure("kubectl apply of non-Job profile resources failed; completion was not proven")

        runtime_secret = _bootstrap_runtime_secret(
            kubectl,
            context,
            namespace,
            normalized_run_id,
            context7_secret_name,
            omniroute_secret_name,
            evidence_dir,
            commands,
        )
        report["runtime_secret"] = runtime_secret
        phase_evidence["runtime-secret"] = _artifact_ref(evidence_dir / "runtime-secret.json", evidence_dir.parent)
        if runtime_secret["status"] != "PASS":
            return finish_apply_failure("temporary runtime Secret bootstrap failed; completion was not proven")
        apply_args = ["apply", "-f", str(evidence_dir / "job-manifest.yaml"), "-o", "name"]
        apply_artifact_name = "apply-job.txt"
    else:
        apply_args = ["apply", "-f", str(manifest_path), "-o", "name"]
        apply_artifact_name = "apply.txt"

    apply_result = run_kubectl(
        kubectl,
        apply_args,
        context=context,
        timeout_seconds=120,
    )
    _record_command(commands, apply_result)
    _write_result_text(evidence_dir / apply_artifact_name, apply_result)
    phase_evidence["apply"] = _artifact_ref(evidence_dir / apply_artifact_name, evidence_dir.parent)
    if not apply_result.ok:
        return finish_apply_failure("kubectl apply of the benchmark Job failed; completion was not proven")

    execution = _wait_for_job(
        kubectl,
        context,
        namespace,
        commands,
        wait_seconds=wait_seconds,
        poll_seconds=poll_seconds,
    )
    report["execution"] = execution
    evidence = _capture_evidence(kubectl, context, namespace, evidence_dir, commands)
    report["evidence"] = {**phase_evidence, **evidence["paths"]}
    report["cleanup"] = _cleanup_namespace(
        kubectl,
        context,
        namespace,
        normalized_run_id,
        evidence_dir,
        commands,
        apply_started=apply_started,
        keep_namespace=keep_namespace,
    )
    cleanup_status = report["cleanup"]["status"]
    if execution["status"] == "PASS" and cleanup_status == "PASS":
        report["status"] = "PASS"
    elif execution["status"] == "BLOCKED" or cleanup_status == "BLOCKED":
        report["status"] = "BLOCKED"
    else:
        report["status"] = "NOT_PROVEN"
    if report["status"] != "PASS":
        report["blockers"].append(report["execution"]["reason"])
        if cleanup_status != "PASS":
            report["blockers"].append(report["cleanup"]["reason"])
    _write_json(report_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--runner-image", default=DEFAULT_RUNNER_IMAGE)
    parser.add_argument("--context", default=DEFAULT_CONTEXT, help="kubectl context; defaults to Docker Desktop")
    parser.add_argument("--kubectl", dest="kubectl_path")
    parser.add_argument("--apply", action="store_true", help="mutate the cluster and run the temporary Job")
    parser.add_argument("--keep-namespace", action="store_true", help="retain the generated namespace for diagnosis")
    parser.add_argument(
        "--bootstrap-runtime-secret",
        action="store_true",
        help="create temporary runtime Secret objects from caller env values or deterministic dummies",
    )
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_WAIT_SECONDS)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--target-namespace", default=DEFAULT_TARGET_NAMESPACE)
    parser.add_argument("--context7-secret-name", default="forgeos-runtime-secrets")
    parser.add_argument("--omniroute-secret-name", default="forgeos-runtime-secrets")
    parser.add_argument("--backend-service", default=DEFAULT_SERVICE_NAMES["backend"])
    parser.add_argument("--redis-service", default=DEFAULT_SERVICE_NAMES["redis"])
    parser.add_argument("--postgres-service", default=DEFAULT_SERVICE_NAMES["postgres"])
    parser.add_argument("--omniroute-service", default=DEFAULT_SERVICE_NAMES["omniroute"])
    parser.add_argument("--dns-service-ip", default=DEFAULT_DNS_SERVICE_IP)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.wait_seconds < 0 or args.poll_seconds < 0:
        parser.error("--wait-seconds and --poll-seconds must be non-negative")
    try:
        normalized_run_id = normalize_run_id(args.run_id)
        output_dir = args.output_dir or ROOT / ".localforge" / "benchmark-profile" / normalized_run_id
        report = run_compliance(
            run_id=normalized_run_id,
            output_dir=output_dir,
            runner_image=args.runner_image,
            apply=args.apply,
            keep_namespace=args.keep_namespace,
            bootstrap_runtime_secret=args.bootstrap_runtime_secret,
            context=args.context,
            kubectl_path=args.kubectl_path,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            project_id=args.project_id,
            target_namespace=args.target_namespace,
            context7_secret_name=args.context7_secret_name,
            omniroute_secret_name=args.omniroute_secret_name,
            backend_service_name=args.backend_service,
            redis_service_name=args.redis_service,
            postgres_service_name=args.postgres_service,
            omniroute_service_name=args.omniroute_service,
            dns_service_ip=args.dns_service_ip,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": report["status"], "report": str(output_dir / "compliance-report.json"), "namespace": report.get("namespace")}, indent=2))
    return _status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
