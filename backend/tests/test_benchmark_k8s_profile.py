import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.run_kubernetes_profile_compliance as compliance
from scripts.generate_benchmark_k8s_profile import (
    DEFAULT_DNS_SERVICE_IP,
    DNS_EGRESS_PORTS,
    DNS_NAMESPACE_SELECTOR,
    build_profile,
    validate_profile,
)


def _objects(profile):
    return {item["kind"] + "/" + item["metadata"]["name"]: item for item in profile["manifests"]}


def test_profile_contains_isolated_runner_and_safe_boundaries():
    profile = build_profile("test123")
    validate_profile(profile)
    objects = _objects(profile)

    assert "Namespace/forgeos-benchmark-test123" in objects
    assert "ServiceAccount/forgeos-benchmark-runner" in objects
    assert "Role/forgeos-benchmark-runner" in objects
    assert "RoleBinding/forgeos-benchmark-runner" in objects
    assert "ConfigMap/forgeos-benchmark-config" in objects
    assert "PersistentVolumeClaim/forgeos-benchmark-state" in objects
    assert "Job/forgeos-benchmark-runner" in objects
    assert "NetworkPolicy/forgeos-benchmark-default-deny" in objects

    job = objects["Job/forgeos-benchmark-runner"]
    pod_spec = job["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert pod_spec["restartPolicy"] == "OnFailure"
    assert container["command"] == ["localforge"]
    assert container["args"][:2] == ["benchmark", "report"]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert "pids" not in container["resources"]["limits"]
    assert job["metadata"]["annotations"]["forgeos.io/pids-limit"] == "256"
    assert job["spec"]["template"]["metadata"]["annotations"]["forgeos.io/pids-limit"] == "256"
    assert {item["name"] for item in container["env"]} >= {
        "CONTEXT7_API_KEY",
        "OMNIROUTE_API_KEY",
        "LOCALFORGE_API_TOKEN",
        "REDIS_PASSWORD",
        "POSTGRES_PASSWORD",
    }
    assert profile["targets"]["namespace"] == "forgeos"
    assert profile["targets"]["services"] == {
        "backend": "forgeos-forgeos-cloud-backend",
        "redis": "forgeos-forgeos-cloud-redis",
        "postgres": "forgeos-forgeos-cloud-postgres",
        "omniroute": "forgeos-forgeos-cloud-omniroute",
    }
    configmap = objects["ConfigMap/forgeos-benchmark-config"]["data"]
    assert configmap["FORGEOS_BACKEND_URL"] == "http://forgeos-forgeos-cloud-backend.forgeos.svc.cluster.local:8000"
    assert configmap["REDIS_HOST"] == "forgeos-forgeos-cloud-redis.forgeos.svc.cluster.local"
    assert configmap["POSTGRES_HOST"] == "forgeos-forgeos-cloud-postgres.forgeos.svc.cluster.local"
    assert configmap["OMNIROUTE_URL"] == "http://forgeos-forgeos-cloud-omniroute.forgeos.svc.cluster.local:20128/v1"
    assert profile["evidence"]["path"] == "/var/lib/forgeos/evidence"
    assert profile["runner"]["pids_limit"] == 256
    assert profile["runner"]["pids_limit_annotation"] == "forgeos.io/pids-limit"

    rendered = yaml.safe_dump_all(profile["manifests"], sort_keys=False)
    assert "hostPath" not in rendered
    assert "privileged: true" not in rendered
    assert "hostNetwork: true" not in rendered
    assert "hostPID: true" not in rendered
    assert "REPLACE_AT_RUNTIME" not in rendered
    assert "CONTEXT7_API_KEY" in rendered
    assert "OMNIROUTE_API_KEY" in rendered
    assert "forgeos-forgeos-cloud-redis" in rendered
    assert "forgeos-forgeos-cloud-omniroute" in rendered


def test_profile_is_deterministic_and_rejects_unsafe_mutation():
    first = build_profile("fixed-run")
    second = build_profile("fixed-run")
    assert first == second

    second["manifests"][0]["metadata"]["name"] = "unsafe"
    try:
        validate_profile(second)
    except ValueError as exc:
        assert "namespace" in str(exc).lower()
    else:
        raise AssertionError("mutated namespace was accepted")


def test_profile_validator_requires_pids_metadata_instead_of_invalid_resource_key():
    profile = build_profile("pids123")
    container = profile["manifests"][7]["spec"]["template"]["spec"]["containers"][0]
    container["resources"]["limits"]["pids"] = "256"
    try:
        validate_profile(profile)
    except ValueError as exc:
        assert "forgeos.io/pids-limit" in str(exc)
    else:
        raise AssertionError("invalid container pids resource was accepted")


def test_profile_declares_least_privilege_dns_service_ip_block_and_selector():
    profile = build_profile("dns123")
    validate_profile(profile)
    policy = _objects(profile)["NetworkPolicy/forgeos-benchmark-default-deny"]
    dns_ports = [dict(item) for item in DNS_EGRESS_PORTS]
    egress = policy["spec"]["egress"]

    assert {
        "service_ip": DEFAULT_DNS_SERVICE_IP,
        "ip_block": f"{DEFAULT_DNS_SERVICE_IP}/32",
        "namespace_selector": DNS_NAMESPACE_SELECTOR,
        "ports": dns_ports,
    } == profile["resource_bounds"]["dns"]
    assert {
        "to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": DNS_NAMESPACE_SELECTOR}}}],
        "ports": dns_ports,
    } in egress
    assert {"to": [{"ipBlock": {"cidr": f"{DEFAULT_DNS_SERVICE_IP}/32"}}], "ports": dns_ports} in egress

    compliance_result = compliance.validate_profile_for_compliance(profile)
    assert compliance_result["checks"]["network_policy_dns"]["status"] == "PASS"

    custom_profile = build_profile("dnscustom", dns_service_ip="10.96.0.53")
    validate_profile(custom_profile)
    custom_policy = _objects(custom_profile)["NetworkPolicy/forgeos-benchmark-default-deny"]
    assert {"to": [{"ipBlock": {"cidr": "10.96.0.53/32"}}], "ports": dns_ports} in custom_policy["spec"]["egress"]


def test_profile_validator_rejects_missing_dns_service_ip_block():
    profile = build_profile("dnsmissing")
    policy = _objects(profile)["NetworkPolicy/forgeos-benchmark-default-deny"]
    policy["spec"]["egress"] = [
        rule for rule in policy["spec"]["egress"] if not any("ipBlock" in destination for destination in rule.get("to", []))
    ]

    try:
        validate_profile(profile)
    except ValueError as exc:
        assert "ipBlock" in str(exc)
    else:
        raise AssertionError("missing DNS service IP block was accepted")


def test_profile_validator_rejects_short_cross_namespace_service_endpoints():
    profile = build_profile("fqdnmissing")
    configmap = _objects(profile)["ConfigMap/forgeos-benchmark-config"]
    configmap["data"]["REDIS_HOST"] = "forgeos-forgeos-cloud-redis"

    try:
        validate_profile(profile)
    except ValueError as exc:
        assert "FQDN" in str(exc)
    else:
        raise AssertionError("short cross-namespace service endpoint was accepted")


def test_profile_cli_writes_manifest_and_metadata(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_benchmark_k8s_profile.py",
            "--run-id",
            "cli123",
            "--output-dir",
            str(tmp_path),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "manifest.yaml").is_file()
    metadata = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert metadata["namespace"] == "forgeos-benchmark-cli123"
    assert metadata["secret_values_versioned"] is False
    assert metadata["runner"]["unprivileged"] is True
    assert metadata["runner"]["restart_policy"] == "OnFailure"


def test_compliance_profile_checks_and_redaction_are_fail_closed():
    profile = build_profile("compliance123", runner_image="localforge/runner:test")
    result = compliance.validate_profile_for_compliance(profile)

    assert result["status"] == "PASS"
    assert result["checks"]["unprivileged"]["status"] == "PASS"
    assert result["checks"]["read_only_root_filesystem"]["status"] == "PASS"
    assert result["checks"]["no_hostpath_or_host_namespace_access"]["status"] == "PASS"
    assert result["checks"]["cross_namespace_service_fqdns"]["status"] == "PASS"

    logs = compliance.redact_job_logs(
        "starting benchmark\nCONTEXT7_API_KEY=ctx7-secret-value\nfinished\n"
    )
    assert "ctx7-secret-value" not in logs
    assert "starting benchmark" in logs
    assert "finished" in logs

    payload = compliance.redact_json_payload(
        {"kind": "Pod", "metadata": {"name": "runner"}, "api_key": "json-secret-value"}
    )
    assert "json-secret-value" not in json.dumps(payload)

    unsafe = json.loads(json.dumps(profile))
    unsafe["manifests"][0]["metadata"]["labels"]["forgeos.io/run-id"] = "different"
    unsafe_result = compliance.validate_profile_for_compliance(unsafe)
    assert unsafe_result["status"] == "BLOCKED"
    assert "namespace_identity" in unsafe_result["failed_checks"]


def test_job_completion_requires_completed_job_and_succeeded_pod():
    complete_job = {
        "status": {
            "succeeded": 1,
            "conditions": [{"type": "Complete", "status": "True"}],
        }
    }
    succeeded_pod = {"items": [{"status": {"phase": "Succeeded"}}]}
    assert compliance.evaluate_job_completion(complete_job, succeeded_pod)["status"] == "PASS"

    image_pull_pod = {
        "items": [
            {
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [{"state": {"waiting": {"reason": "ImagePullBackOff"}}}],
                }
            }
        ]
    }
    blocked = compliance.evaluate_job_completion({"status": {}}, image_pull_pod)
    assert blocked["status"] == "BLOCKED"
    assert compliance.evaluate_job_completion({"status": {}}, {"items": []})["status"] == "NOT_PROVEN"


def test_runtime_secret_bootstrap_uses_env_or_dummy_without_artifact_values(tmp_path, monkeypatch):
    captured_inputs = []

    def fake_run_kubectl(kubectl, args, **kwargs):
        captured_inputs.append(kwargs.get("input_text"))
        return compliance.KubectlResult(("kubectl", *args), 0, "secret/forgeos-runtime-secrets configured\n", "")

    monkeypatch.setenv("CONTEXT7_API_KEY", "caller-secret-value")
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    monkeypatch.setattr(compliance, "_workspace_env_values", lambda: {})
    monkeypatch.setattr(compliance, "run_kubectl", fake_run_kubectl)
    result = compliance._bootstrap_runtime_secret(
        "kubectl",
        "docker-desktop",
        "forgeos-benchmark-secret123",
        "secret123",
        "forgeos-runtime-secrets",
        "forgeos-runtime-secrets",
        tmp_path,
        [],
    )

    assert result["status"] == "PASS"
    source_by_key = {item["key"]: item["source"] for item in result["value_sources"]}
    assert source_by_key["CONTEXT7_API_KEY"] == "caller-environment"
    assert source_by_key["OMNIROUTE_API_KEY"] == "deterministic-dummy"
    assert any("caller-secret-value" in value for value in captured_inputs if value)
    artifact = (tmp_path / "runtime-secret.json").read_text(encoding="utf-8")
    assert "caller-secret-value" not in artifact
    assert "forgeos-compliance-dummy-" not in artifact


def test_runtime_secret_bootstrap_loads_workspace_dotenv_without_persisting_values(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OMNIROUTE_API_KEY=dotenv-omniroute-value\n"
        "LOCALFORGE_API_TOKEN=dotenv-localforge-value\n"
        "REDIS_PASSWORD=dotenv-redis-value\n"
        "POSTGRES_PASSWORD=dotenv-postgres-value\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(compliance, "ROOT", tmp_path)
    for key in compliance.RUNTIME_SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONTEXT7_API_KEY", "caller-context7-value")

    captured_inputs = []

    def fake_run_kubectl(kubectl, args, **kwargs):
        captured_inputs.append(kwargs.get("input_text"))
        return compliance.KubectlResult(("kubectl", *args), 0, "secret/forgeos-runtime-secrets configured\n", "")

    monkeypatch.setattr(compliance, "run_kubectl", fake_run_kubectl)
    result = compliance._bootstrap_runtime_secret(
        "kubectl",
        "docker-desktop",
        "forgeos-benchmark-dotenv123",
        "dotenv123",
        "forgeos-runtime-secrets",
        "forgeos-runtime-secrets",
        tmp_path,
        [],
    )

    source_by_key = {item["key"]: item["source"] for item in result["value_sources"]}
    assert source_by_key["CONTEXT7_API_KEY"] == "caller-environment"
    assert source_by_key["OMNIROUTE_API_KEY"] == "workspace-dotenv"
    assert source_by_key["LOCALFORGE_API_TOKEN"] == "workspace-dotenv"
    assert source_by_key["REDIS_PASSWORD"] == "workspace-dotenv"
    assert source_by_key["POSTGRES_PASSWORD"] == "workspace-dotenv"
    assert result["values_persisted"] is False
    assert any("dotenv-omniroute-value" in value for value in captured_inputs if value)
    artifact = (tmp_path / "runtime-secret.json").read_text(encoding="utf-8")
    assert "caller-context7-value" not in artifact
    assert "dotenv-" not in artifact


def test_cleanup_requires_exact_namespace_identity_and_verifies_absence(tmp_path, monkeypatch):
    calls = []
    namespace = "forgeos-benchmark-clean123"

    def fake_run_kubectl(kubectl, args, **kwargs):
        calls.append(list(args))
        if args[:3] == ["get", "namespace", namespace] and "-o" in args and "json" in args:
            return compliance.KubectlResult(
                ("kubectl", *args),
                0,
                json.dumps(
                    {
                        "metadata": {
                            "name": namespace,
                            "labels": {
                                "app.kubernetes.io/part-of": "forgeos-benchmark",
                                "forgeos.io/run-id": "clean123",
                            },
                        }
                    }
                ),
                "",
            )
        if args[:2] == ["delete", "namespace"]:
            return compliance.KubectlResult(("kubectl", *args), 0, "namespace deleted", "")
        if "--ignore-not-found" in args:
            return compliance.KubectlResult(("kubectl", *args), 0, "", "")
        raise AssertionError(f"unexpected kubectl call: {args}")

    monkeypatch.setattr(compliance, "run_kubectl", fake_run_kubectl)
    result = compliance._cleanup_namespace(
        "kubectl",
        "docker-desktop",
        namespace,
        "clean123",
        tmp_path,
        [],
        apply_started=True,
        keep_namespace=False,
    )

    assert result["status"] == "PASS"
    assert calls[1] == ["delete", "namespace", namespace, "--wait=true"]
    assert calls[2] == ["get", "namespace", namespace, "--ignore-not-found", "-o", "name"]


def test_compliance_cli_without_apply_only_dry_runs(tmp_path, monkeypatch):
    calls = []

    def fake_run_kubectl(kubectl, args, **kwargs):
        calls.append(list(args))
        if args[:2] == ["config", "get-contexts"]:
            return compliance.KubectlResult(("kubectl", *args), 0, "docker-desktop\n", "")
        if args[:1] == ["version"]:
            return compliance.KubectlResult(("kubectl", *args), 0, "{}", "")
        if args[:1] == ["apply"]:
            assert "--dry-run=server" in args
            return compliance.KubectlResult(("kubectl", *args), 0, "namespace/forgeos-benchmark-readonly123\n", "")
        raise AssertionError(f"unexpected mutating or unmocked kubectl call: {args}")

    monkeypatch.setattr(compliance, "_find_kubectl", lambda explicit: "kubectl")
    monkeypatch.setattr(compliance, "run_kubectl", fake_run_kubectl)
    report = compliance.run_compliance(
        run_id="readonly123",
        output_dir=tmp_path,
        apply=False,
        wait_seconds=0,
        poll_seconds=0,
    )

    assert report["status"] == "NOT_PROVEN"
    assert not any(call[:2] == ["delete", "namespace"] for call in calls)
    assert (tmp_path / "manifest.sha256").is_file()
    assert (tmp_path / "compliance-report.json").is_file()
    saved_report = json.loads((tmp_path / "compliance-report.json").read_text(encoding="utf-8"))
    assert saved_report["profile"]["checks"]["no_secret_values"]["status"] == "PASS"


def test_runtime_secret_bootstrap_requires_explicit_apply(tmp_path):
    report = compliance.run_compliance(
        run_id="secret-no-apply123",
        output_dir=tmp_path,
        bootstrap_runtime_secret=True,
        apply=False,
    )

    assert report["status"] == "BLOCKED"
    assert "requires explicit --apply" in report["blockers"][0]


def test_apply_path_requires_completion_and_writes_evidence_before_cleanup(tmp_path, monkeypatch):
    namespace = "forgeos-benchmark-live123"
    state = {"created": False, "deleted": False}

    def result(args, code=0, stdout="", stderr=""):
        return compliance.KubectlResult(("kubectl", *args), code, stdout, stderr)

    def fake_run_kubectl(kubectl, args, **kwargs):
        if args[:2] == ["config", "get-contexts"]:
            return result(args, stdout="docker-desktop\n")
        if args[:1] == ["version"]:
            return result(args, stdout="{}")
        if args[:1] == ["apply"]:
            state["created"] = True
            return result(args, stdout="job.batch/forgeos-benchmark-runner created\n")
        if args[:2] == ["delete", "namespace"]:
            state["deleted"] = True
            return result(args, stdout="namespace deleted\n")
        if args[:2] == ["get", "namespace"]:
            if "--ignore-not-found" in args:
                return result(args, stdout="" if state["deleted"] else f"namespace/{namespace}\n")
            if not state["created"]:
                return result(args, code=1, stderr=f'namespaces "{namespace}" not found\n')
            return result(
                args,
                stdout=json.dumps(
                    {
                        "kind": "Namespace",
                        "metadata": {
                            "name": namespace,
                            "labels": {
                                "app.kubernetes.io/part-of": "forgeos-benchmark",
                                "forgeos.io/run-id": "live123",
                            },
                        },
                    }
                ),
            )
        if args[:2] == ["get", "job"]:
            return result(
                args,
                stdout=json.dumps(
                    {
                        "kind": "Job",
                        "status": {
                            "succeeded": 1,
                            "conditions": [{"type": "Complete", "status": "True"}],
                        },
                    }
                ),
            )
        if args[:2] == ["get", "pods"]:
            return result(args, stdout=json.dumps({"kind": "List", "items": [{"status": {"phase": "Succeeded"}}]}))
        if args[:1] == ["get"] and "-o" in args and "json" in args:
            return result(args, stdout=json.dumps({"kind": "Observed", "metadata": {"name": "observed"}}))
        if args[:1] == ["describe"]:
            return result(args, stdout="safe describe output\n")
        if args[:1] == ["auth"]:
            expected = not (
                args[2] in {"create", "delete"}
                or (args[2] in {"get", "list"} and args[3] == "secrets")
            )
            return result(args, code=0 if expected else 1, stdout=("yes\n" if expected else "no\n"))
        if args[:1] == ["logs"]:
            return result(args, stdout="benchmark completed\nCONTEXT7_API_KEY=hidden-secret\n")
        raise AssertionError(f"unexpected kubectl call: {args}")

    monkeypatch.setattr(compliance, "_find_kubectl", lambda explicit: "kubectl")
    monkeypatch.setattr(compliance, "run_kubectl", fake_run_kubectl)
    report = compliance.run_compliance(
        run_id="live123",
        output_dir=tmp_path,
        runner_image="eao_sandbox_alpine:latest",
        apply=True,
        bootstrap_runtime_secret=True,
        context="docker-desktop",
        wait_seconds=0,
        poll_seconds=0,
    )

    assert report["status"] == "PASS"
    assert report["execution"]["status"] == "PASS"
    assert report["cleanup"]["status"] == "PASS"
    assert report["runtime_secret"]["status"] == "PASS"
    assert report["runtime_secret"]["values_persisted"] is False
    saved_report = json.loads((tmp_path / "compliance-report.json").read_text(encoding="utf-8"))
    assert saved_report["runtime_secret"]["status"] == "PASS"
    assert saved_report["evidence"]["runtime-secret"] == "evidence/runtime-secret.json"
    assert state["deleted"] is True
    assert (tmp_path / "evidence" / "pods.json").is_file()
    assert (tmp_path / "evidence" / "job.json").is_file()
    assert (tmp_path / "evidence" / "networkpolicy.json").is_file()
    assert (tmp_path / "evidence" / "rbac-can-i.json").is_file()
    assert (tmp_path / "evidence" / "job.log").is_file()
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file())
    assert "hidden-secret" not in artifact_text
