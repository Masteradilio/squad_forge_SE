"""Generate a least-privilege Kubernetes profile for a ForgeOS benchmark run."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "deploy" / "benchmark" / "kubernetes" / "generated"
SCHEMA = "forgeos.kubernetes_benchmark_profile.v1"
PIDS_LIMIT = 256
PIDS_LIMIT_ANNOTATION = "forgeos.io/pids-limit"
DEFAULT_DNS_SERVICE_IP = "10.96.0.10"
DNS_NAMESPACE_SELECTOR = "kube-system"
DNS_EGRESS_PORTS = (
    {"protocol": "UDP", "port": 53},
    {"protocol": "TCP", "port": 53},
)
SERVICE_DNS_DOMAIN = "svc.cluster.local"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?$")
DEFAULT_TARGET_NAMESPACE = "forgeos"
DEFAULT_SERVICE_NAMES = {
    "backend": "forgeos-forgeos-cloud-backend",
    "redis": "forgeos-forgeos-cloud-redis",
    "postgres": "forgeos-forgeos-cloud-postgres",
    "omniroute": "forgeos-forgeos-cloud-omniroute",
}


def normalize_run_id(value: str) -> str:
    run_id = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    if not run_id or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be a DNS-safe value with at most 40 characters")
    return run_id


def normalize_dns_name(value: str, field_name: str) -> str:
    """Validate a namespace/service name before placing it in a manifest."""
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 63 or not DNS_LABEL_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a DNS-safe value with at most 63 characters")
    return normalized


def normalize_dns_service_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError("dns_service_ip must be a valid IPv4 address") from exc
    if address.version != 4:
        raise ValueError("dns_service_ip must be a valid IPv4 address")
    return str(address)


def service_fqdn(service_name: str, namespace: str) -> str:
    return f"{service_name}.{namespace}.{SERVICE_DNS_DOMAIN}"


def _metadata(
    name: str,
    namespace: str,
    labels: dict[str, str],
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"name": name, "namespace": namespace, "labels": labels}
    if annotations:
        metadata["annotations"] = annotations
    return metadata


def build_profile(
    run_id: str,
    *,
    context7_secret_name: str = "forgeos-runtime-secrets",
    omniroute_secret_name: str = "forgeos-runtime-secrets",
    target_namespace: str = DEFAULT_TARGET_NAMESPACE,
    backend_service_name: str = DEFAULT_SERVICE_NAMES["backend"],
    redis_service_name: str = DEFAULT_SERVICE_NAMES["redis"],
    postgres_service_name: str = DEFAULT_SERVICE_NAMES["postgres"],
    omniroute_service_name: str = DEFAULT_SERVICE_NAMES["omniroute"],
    runner_image: str = "localforge/forgeos-benchmark-runner:dev",
    project_id: int = 1,
    dns_service_ip: str = DEFAULT_DNS_SERVICE_IP,
) -> dict[str, Any]:
    run_id = normalize_run_id(run_id)
    namespace = f"forgeos-benchmark-{run_id}"
    context7_secret_name = normalize_dns_name(context7_secret_name, "context7_secret_name")
    omniroute_secret_name = normalize_dns_name(omniroute_secret_name, "omniroute_secret_name")
    target_namespace = normalize_dns_name(target_namespace, "target_namespace")
    service_names = {
        "backend": normalize_dns_name(backend_service_name, "backend_service_name"),
        "redis": normalize_dns_name(redis_service_name, "redis_service_name"),
        "postgres": normalize_dns_name(postgres_service_name, "postgres_service_name"),
        "omniroute": normalize_dns_name(omniroute_service_name, "omniroute_service_name"),
    }
    service_fqdns = {key: service_fqdn(value, target_namespace) for key, value in service_names.items()}
    dns_service_ip = normalize_dns_service_ip(dns_service_ip)
    dns_service_ip_block = f"{dns_service_ip}/32"
    if not runner_image.strip() or "\n" in runner_image or "\r" in runner_image:
        raise ValueError("runner_image must be a non-empty single-line image reference")
    if project_id < 1:
        raise ValueError("project_id must be a positive integer")
    labels = {
        "app.kubernetes.io/part-of": "forgeos-benchmark",
        "forgeos.io/run-id": run_id,
    }
    namespaced_labels = {**labels, "forgeos.io/benchmark-runner": "true"}
    manifests: list[dict[str, Any]] = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace, "labels": labels},
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": _metadata("forgeos-benchmark-runner", namespace, namespaced_labels),
            "automountServiceAccountToken": True,
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": _metadata("forgeos-benchmark-runner", namespace, labels),
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["pods", "pods/log", "events", "services", "configmaps"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": ["deployments", "statefulsets"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["batch"],
                    "resources": ["jobs"],
                    "verbs": ["get", "list", "watch"],
                },
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": _metadata("forgeos-benchmark-runner", namespace, labels),
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "forgeos-benchmark-runner",
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "forgeos-benchmark-runner",
                    "namespace": namespace,
                }
            ],
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": _metadata("forgeos-benchmark-config", namespace, labels),
            "data": {
                "FORGEOS_BENCHMARK_SCHEMA": SCHEMA,
                "FORGEOS_BENCHMARK_RUN_ID": run_id,
                "FORGEOS_BENCHMARK_NAMESPACE": namespace,
                "LOCALFORGE_ENV": "benchmark",
                "LOCALFORGE_MAX_RUN_TIME": "5400",
                "LOCALFORGE_MAX_TASK_DURATION": "900",
                "LOCALFORGE_MAX_PARALLEL_TASKS": "2",
                "LOCALFORGE_MAX_ACTIVE_MODEL_CALLS": "4",
                "FORGEOS_BENCHMARK_EXECUTION_SCOPE": "kubernetes-pod",
                "FORGEOS_BENCHMARK_EVIDENCE_SCHEMA": "forgeos.kubernetes_benchmark_evidence.v1",
                "FORGEOS_BENCHMARK_EVIDENCE_DIR": "/var/lib/forgeos/evidence",
                "FORGEOS_BENCHMARK_RESULT_FILE": "/var/lib/forgeos/evidence/benchmark.json",
                "FORGEOS_BENCHMARK_PROJECT_ID": str(project_id),
                "FORGEOS_BENCHMARK_TARGET_NAMESPACE": target_namespace,
                "FORGEOS_BACKEND_URL": f"http://{service_fqdns['backend']}:8000",
                "REDIS_HOST": service_fqdns["redis"],
                "REDIS_PORT": "6379",
                "REDIS_DB": "0",
                "POSTGRES_HOST": service_fqdns["postgres"],
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "forgeos",
                "POSTGRES_USER": "forgeos",
                "CONTEXT7_ENABLED": "true",
                "CONTEXT7_MCP_ENDPOINT": "https://mcp.context7.com/mcp",
                "OMNIROUTE_URL": f"http://{service_fqdns['omniroute']}:20128/v1",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": _metadata("forgeos-benchmark-quota", namespace, labels),
            "spec": {
                "hard": {
                    "requests.cpu": "4",
                    "limits.cpu": "8",
                    "requests.memory": "8Gi",
                    "limits.memory": "12Gi",
                    "pods": "12",
                    "persistentvolumeclaims": "2",
                }
            },
        },
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": _metadata("forgeos-benchmark-state", namespace, labels),
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "5Gi"}},
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": _metadata(
                "forgeos-benchmark-runner",
                namespace,
                namespaced_labels,
                {PIDS_LIMIT_ANNOTATION: str(PIDS_LIMIT)},
            ),
            "spec": {
                "backoffLimit": 2,
                "activeDeadlineSeconds": 5400,
                "ttlSecondsAfterFinished": 86400,
                "template": {
                    "metadata": {
                        "labels": namespaced_labels,
                        "annotations": {PIDS_LIMIT_ANNOTATION: str(PIDS_LIMIT)},
                    },
                    "spec": {
                        "serviceAccountName": "forgeos-benchmark-runner",
                        "automountServiceAccountToken": True,
                        "restartPolicy": "OnFailure",
                        "activeDeadlineSeconds": 5400,
                        "terminationGracePeriodSeconds": 30,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 10001,
                            "runAsGroup": 10001,
                            "fsGroup": 10001,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "runner",
                                "image": runner_image,
                                "imagePullPolicy": "IfNotPresent",
                                "workingDir": "/work",
                                "command": ["localforge"],
                                "args": ["benchmark", "report", "--project-id", str(project_id)],
                                "envFrom": [{"configMapRef": {"name": "forgeos-benchmark-config"}}],
                                "env": [
                                    {
                                        "name": "CONTEXT7_API_KEY",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": context7_secret_name,
                                                "key": "CONTEXT7_API_KEY",
                                                "optional": False,
                                            }
                                        },
                                    },
                                    {
                                        "name": "OMNIROUTE_API_KEY",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": omniroute_secret_name,
                                                "key": "OMNIROUTE_API_KEY",
                                                "optional": False,
                                            }
                                        },
                                    },
                                    {
                                        "name": "LOCALFORGE_API_TOKEN",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": omniroute_secret_name,
                                                "key": "LOCALFORGE_API_TOKEN",
                                                "optional": False,
                                            }
                                        },
                                    },
                                    {
                                        "name": "REDIS_PASSWORD",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": omniroute_secret_name,
                                                "key": "REDIS_PASSWORD",
                                                "optional": False,
                                            }
                                        },
                                    },
                                    {
                                        "name": "POSTGRES_PASSWORD",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": omniroute_secret_name,
                                                "key": "POSTGRES_PASSWORD",
                                                "optional": False,
                                            }
                                        },
                                    },
                                ],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "resources": {
                                    "requests": {
                                        "cpu": "500m",
                                        "memory": "1Gi",
                                        "ephemeral-storage": "1Gi",
                                    },
                                    "limits": {
                                        "cpu": "2",
                                        "memory": "4Gi",
                                        "ephemeral-storage": "4Gi",
                                    },
                                },
                                "volumeMounts": [
                                    {"name": "worktrees", "mountPath": "/workspace"},
                                    {"name": "workdir", "mountPath": "/work"},
                                    {"name": "state", "mountPath": "/var/lib/forgeos"},
                                    {"name": "tmp", "mountPath": "/tmp"},
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": "worktrees", "emptyDir": {"sizeLimit": "4Gi"}},
                            {"name": "workdir", "emptyDir": {"sizeLimit": "2Gi"}},
                            {"name": "tmp", "emptyDir": {"sizeLimit": "1Gi"}},
                            {
                                "name": "state",
                                "persistentVolumeClaim": {"claimName": "forgeos-benchmark-state"},
                            },
                        ],
                    },
                },
            },
        },
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": _metadata("forgeos-benchmark-default-deny", namespace, labels),
            "spec": {
                "podSelector": {"matchLabels": {"forgeos.io/benchmark-runner": "true"}},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [],
                "egress": [
                    {
                        "to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": target_namespace}}}],
                        "ports": [
                            {"protocol": "TCP", "port": 8000},
                            {"protocol": "TCP", "port": 6379},
                            {"protocol": "TCP", "port": 5432},
                            {"protocol": "TCP", "port": 20128},
                        ],
                    },
                    {
                        "to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": DNS_NAMESPACE_SELECTOR}}}],
                        "ports": [
                            {"protocol": "UDP", "port": 53},
                            {"protocol": "TCP", "port": 53},
                        ],
                    },
                    {
                        "to": [{"ipBlock": {"cidr": dns_service_ip_block}}],
                        "ports": [
                            {"protocol": "UDP", "port": 53},
                            {"protocol": "TCP", "port": 53},
                        ],
                    },
                    {
                        "ports": [{"protocol": "TCP", "port": 443}],
                    },
                ],
            },
        },
    ]
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "namespace": namespace,
        "secret_values_versioned": False,
        "resource_bounds": {
            "active_deadline_seconds": 5400,
            "task_deadline_seconds": 900,
            "parallel_tasks": 2,
            "max_active_model_calls": 4,
            "pids_limit": PIDS_LIMIT,
            "pids_limit_annotation": PIDS_LIMIT_ANNOTATION,
            "pids_limit_enforcement": "metadata-only; Kubernetes v1.34 rejects pids as a standard container resource",
            "egress": ["namespace services", "cluster DNS", "declared HTTPS connectors"],
            "dns": {
                "service_ip": dns_service_ip,
                "ip_block": dns_service_ip_block,
                "namespace_selector": DNS_NAMESPACE_SELECTOR,
                "ports": [dict(item) for item in DNS_EGRESS_PORTS],
            },
        },
        "targets": {
            "namespace": target_namespace,
            "services": service_names,
            "service_fqdns": service_fqdns,
        },
        "runner": {
            "image": runner_image,
            "command": ["localforge", "benchmark", "report", "--project-id", str(project_id)],
            "restart_policy": "OnFailure",
            "unprivileged": True,
            "evidence_path": "/var/lib/forgeos/evidence",
            "pids_limit": PIDS_LIMIT,
            "pids_limit_annotation": PIDS_LIMIT_ANNOTATION,
        },
        "evidence": {
            "schema": "forgeos.kubernetes_benchmark_evidence.v1",
            "path": "/var/lib/forgeos/evidence",
            "readiness_failure": "NOT_PROVEN until a controlled rollout failure is observed",
            "rollback": "NOT_PROVEN until helm history contains a verified rollback revision",
            "hpa": "NOT_PROVEN when metrics.k8s.io is unavailable",
        },
        "cleanup": {
            "policy": "ttl-after-finished then explicit namespace deletion",
            "command": f"kubectl delete namespace {namespace} --wait=true",
        },
        "manifests": manifests,
    }


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema") != SCHEMA:
        raise ValueError("unsupported Kubernetes benchmark profile schema")
    run_id = profile.get("run_id")
    namespace = profile.get("namespace")
    if not isinstance(run_id, str) or normalize_run_id(run_id) != run_id:
        raise ValueError("profile run_id is not DNS-safe")
    if namespace != f"forgeos-benchmark-{run_id}":
        raise ValueError("profile namespace does not match run_id")
    targets = profile.get("targets")
    if not isinstance(targets, dict):
        raise ValueError("profile has no target service boundary")
    target_namespace = targets.get("namespace")
    if not isinstance(target_namespace, str):
        raise ValueError("profile target namespace is missing")
    normalize_dns_name(target_namespace, "target_namespace")
    services = targets.get("services")
    if not isinstance(services, dict) or set(services) != set(DEFAULT_SERVICE_NAMES):
        raise ValueError("profile must declare backend, redis, postgres, and omniroute services")
    for key, value in services.items():
        if not isinstance(value, str):
            raise ValueError(f"profile service name is invalid: {key}")
        normalize_dns_name(value, f"{key}_service_name")
    expected_service_fqdns = {key: service_fqdn(value, target_namespace) for key, value in services.items()}
    if targets.get("service_fqdns") != expected_service_fqdns:
        raise ValueError("profile target service FQDN evidence is missing or inconsistent")
    manifests = profile.get("manifests")
    if not isinstance(manifests, list) or not manifests:
        raise ValueError("profile has no Kubernetes manifests")
    required = {
        "Namespace",
        "ServiceAccount",
        "Role",
        "RoleBinding",
        "ConfigMap",
        "ResourceQuota",
        "PersistentVolumeClaim",
        "Job",
        "NetworkPolicy",
    }
    observed = {str(item.get("kind")) for item in manifests}
    missing = required - observed
    if missing:
        raise ValueError(f"profile is missing Kubernetes kinds: {sorted(missing)}")
    serialized = yaml.safe_dump_all(manifests, sort_keys=False)
    for forbidden in ("hostPath", "hostNetwork: true", "hostPID: true", "hostIPC: true", "privileged: true"):
        if forbidden in serialized:
            raise ValueError(f"unsafe Kubernetes field present: {forbidden}")
    if "stringData:" in serialized or ("data:" in serialized and "Secret" in serialized):
        raise ValueError("literal Secret data must not be included in the profile")
    configmaps = [item for item in manifests if item.get("kind") == "ConfigMap"]
    configmap_data = configmaps[0].get("data", {}) if configmaps else {}
    required_config = {
        "FORGEOS_BENCHMARK_EXECUTION_SCOPE",
        "FORGEOS_BENCHMARK_EVIDENCE_DIR",
        "FORGEOS_BENCHMARK_RESULT_FILE",
        "FORGEOS_BENCHMARK_TARGET_NAMESPACE",
        "REDIS_HOST",
        "POSTGRES_HOST",
        "OMNIROUTE_URL",
    }
    if not required_config.issubset(configmap_data):
        raise ValueError("benchmark ConfigMap is missing runtime configuration")
    expected_config = {
        "FORGEOS_BACKEND_URL": f"http://{expected_service_fqdns['backend']}:8000",
        "REDIS_HOST": expected_service_fqdns["redis"],
        "POSTGRES_HOST": expected_service_fqdns["postgres"],
        "OMNIROUTE_URL": f"http://{expected_service_fqdns['omniroute']}:20128/v1",
    }
    if any(configmap_data.get(key) != value for key, value in expected_config.items()):
        raise ValueError("benchmark ConfigMap must use cross-namespace service FQDNs")
    jobs = [item for item in manifests if item.get("kind") == "Job"]
    if len(jobs) != 1:
        raise ValueError("profile must contain exactly one benchmark Job")
    pod_spec = jobs[0].get("spec", {}).get("template", {}).get("spec", {})
    if pod_spec.get("restartPolicy") != "OnFailure":
        raise ValueError("benchmark Job must reconcile failed runner containers")
    if pod_spec.get("serviceAccountName") != "forgeos-benchmark-runner":
        raise ValueError("benchmark Job must use the namespaced runner ServiceAccount")
    container = (pod_spec.get("containers") or [{}])[0]
    if container.get("command") != ["localforge"] or container.get("args", [])[:2] != ["benchmark", "report"]:
        raise ValueError("benchmark Job must execute the benchmark command")
    security = container.get("securityContext", {})
    if security.get("allowPrivilegeEscalation") is not False:
        raise ValueError("benchmark runner must disable privilege escalation")
    if security.get("readOnlyRootFilesystem") is not True:
        raise ValueError("benchmark runner must use a read-only root filesystem")
    if "ALL" not in security.get("capabilities", {}).get("drop", []):
        raise ValueError("benchmark runner must drop all Linux capabilities")
    limits = container.get("resources", {}).get("limits", {})
    if not {"cpu", "memory", "ephemeral-storage"}.issubset(limits):
        raise ValueError("benchmark runner resource limits are incomplete")
    if "pids" in limits:
        raise ValueError("pids must be represented by forgeos.io/pids-limit metadata, not a container resource")
    pids_limit = profile.get("resource_bounds", {}).get("pids_limit")
    if pids_limit != PIDS_LIMIT or profile.get("runner", {}).get("pids_limit") != pids_limit:
        raise ValueError("profile pids_limit evidence is missing or inconsistent")
    job_metadata = jobs[0].get("metadata", {})
    template_metadata = jobs[0].get("spec", {}).get("template", {}).get("metadata", {})
    for metadata_name, metadata in (("Job", job_metadata), ("Pod template", template_metadata)):
        if metadata.get("annotations", {}).get(PIDS_LIMIT_ANNOTATION) != str(pids_limit):
            raise ValueError(f"{metadata_name} must declare {PIDS_LIMIT_ANNOTATION}={pids_limit}")
    resource_bounds = profile.get("resource_bounds")
    dns_config = resource_bounds.get("dns") if isinstance(resource_bounds, dict) else None
    if not isinstance(dns_config, dict):
        raise ValueError("profile DNS egress evidence is missing")
    dns_service_ip = dns_config.get("service_ip")
    if not isinstance(dns_service_ip, str):
        raise ValueError("profile DNS service IP evidence is missing")
    dns_service_ip = normalize_dns_service_ip(dns_service_ip)
    dns_service_ip_block = f"{dns_service_ip}/32"
    dns_ports = [dict(item) for item in DNS_EGRESS_PORTS]
    if (
        dns_config.get("ip_block") != dns_service_ip_block
        or dns_config.get("namespace_selector") != DNS_NAMESPACE_SELECTOR
        or dns_config.get("ports") != dns_ports
    ):
        raise ValueError("profile DNS egress evidence is inconsistent")
    secret_refs = {
        item.get("name"): item.get("valueFrom", {}).get("secretKeyRef", {}).get("key")
        for item in container.get("env", [])
        if item.get("valueFrom", {}).get("secretKeyRef")
    }
    for key in ("CONTEXT7_API_KEY", "OMNIROUTE_API_KEY", "LOCALFORGE_API_TOKEN", "REDIS_PASSWORD", "POSTGRES_PASSWORD"):
        if key not in secret_refs.values():
            raise ValueError(f"benchmark runner is missing runtime Secret reference: {key}")
    policies = [item for item in manifests if item.get("kind") == "NetworkPolicy"]
    policy = policies[0] if policies else {}
    egress = policy.get("spec", {}).get("egress", [])
    target_selector = {"kubernetes.io/metadata.name": target_namespace}
    if not any(
        all(
            item.get("to", [{}])[0].get("namespaceSelector", {}).get("matchLabels", {}).get(key) == value
            for key, value in target_selector.items()
        )
        for item in egress
    ):
        raise ValueError("benchmark egress does not declare the target namespace")
    if not any(
        item.get("to") == [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": DNS_NAMESPACE_SELECTOR}}}]
        and item.get("ports") == dns_ports
        for item in egress
    ):
        raise ValueError("benchmark egress must retain the kube-system DNS namespace selector")
    if not any(
        item.get("to") == [{"ipBlock": {"cidr": dns_service_ip_block}}]
        and item.get("ports") == dns_ports
        for item in egress
    ):
        raise ValueError(f"benchmark egress must allow DNS service ipBlock {dns_service_ip_block}")
    for manifest in manifests:
        metadata = manifest.get("metadata", {})
        if manifest.get("kind") == "Namespace" and metadata.get("name") != namespace:
            raise ValueError("namespace manifest does not match profile namespace")
        if manifest.get("kind") != "Namespace" and metadata.get("namespace") != namespace:
            raise ValueError(f"namespaced manifest is outside benchmark namespace: {manifest.get('kind')}")


def write_outputs(output_dir: Path, profile: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.yaml"
    manifest_path.write_text(
        "---\n".join(yaml.safe_dump(item, sort_keys=False) for item in profile["manifests"]),
        encoding="utf-8",
    )
    metadata = {key: value for key, value in profile.items() if key != "manifests"}
    metadata["manifest"] = "manifest.yaml"
    (output_dir / "profile.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--context7-secret-name", default="forgeos-runtime-secrets")
    parser.add_argument("--omniroute-secret-name", default="forgeos-runtime-secrets")
    parser.add_argument("--target-namespace", default=DEFAULT_TARGET_NAMESPACE)
    parser.add_argument("--backend-service", default=DEFAULT_SERVICE_NAMES["backend"])
    parser.add_argument("--redis-service", default=DEFAULT_SERVICE_NAMES["redis"])
    parser.add_argument("--postgres-service", default=DEFAULT_SERVICE_NAMES["postgres"])
    parser.add_argument("--omniroute-service", default=DEFAULT_SERVICE_NAMES["omniroute"])
    parser.add_argument("--runner-image", default="localforge/forgeos-benchmark-runner:dev")
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--dns-service-ip", default=DEFAULT_DNS_SERVICE_IP)
    parser.add_argument("--check", action="store_true", help="validate and write the profile")
    args = parser.parse_args()
    profile = build_profile(
        args.run_id,
        context7_secret_name=args.context7_secret_name,
        omniroute_secret_name=args.omniroute_secret_name,
        target_namespace=args.target_namespace,
        backend_service_name=args.backend_service,
        redis_service_name=args.redis_service,
        postgres_service_name=args.postgres_service,
        omniroute_service_name=args.omniroute_service,
        runner_image=args.runner_image,
        project_id=args.project_id,
        dns_service_ip=args.dns_service_ip,
    )
    validate_profile(profile)
    write_outputs(args.output_dir, profile)
    print(json.dumps({"schema": SCHEMA, "run_id": profile["run_id"], "namespace": profile["namespace"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
