from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "forgeos-cloud"


def _read_values() -> dict:
    return yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))


def test_helm_values_define_runtime_secret_and_security_contract():
    values = _read_values()

    assert values["serviceAccount"]["create"] is True
    assert values["secrets"]["existingSecret"]
    assert values["redis"]["auth"]["existingSecret"]
    assert values["redis"]["persistence"]["enabled"] is True
    assert values["backend"]["securityContext"]["runAsNonRoot"] is True
    assert values["backend"]["probes"]["readiness"]["path"]
    assert values["deploymentEvidence"]["enabled"] is True
    assert values["deploymentEvidence"]["path"] == "/var/lib/forgeos/evidence"
    assert values["autoscaling"]["metricsServerRequired"] is True


def test_helm_templates_include_services_probes_rbac_network_and_stateful_redis():
    template_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CHART / "templates").glob("*.yaml")
    )

    for expected in (
        "kind: ServiceAccount",
        "kind: Role",
        "kind: RoleBinding",
        "kind: NetworkPolicy",
        "kind: ConfigMap",
        "kind: StatefulSet",
        "readinessProbe:",
        "livenessProbe:",
        "secretKeyRef:",
        "volumeClaimTemplates:",
        "progressDeadlineSeconds:",
        "forgeos.io/readiness-failure-path",
        "helm rollback",
        "metrics.k8s.io",
    ):
        assert expected in template_text
    assert "hostPath" not in template_text


def test_helm_evidence_contract_is_fail_closed_by_definition():
    evidence = (CHART / "templates" / "deployment-evidence.yaml").read_text(encoding="utf-8")

    assert "readiness_failure_path" in evidence
    assert "rollback_command" in evidence
    assert "NOT_PROVEN" in evidence
    assert "Secret" not in evidence


def test_helm_uses_component_credentials_for_url_encoding_at_runtime():
    configmap = (CHART / "templates" / "configmap.yaml").read_text(encoding="utf-8")
    backend = (CHART / "templates" / "deployment-backend.yaml").read_text(encoding="utf-8")

    for expected in ("POSTGRES_HOST:", "POSTGRES_PORT:", "POSTGRES_DB:", "REDIS_HOST:", "REDIS_PORT:"):
        assert expected in configmap
    assert "$(POSTGRES_PASSWORD)" not in backend
    assert "$(REDIS_PASSWORD)" not in backend
    assert "/app/.localforge" in backend
    assert "/tmp" in backend


def test_helm_frontend_allows_non_root_nginx_runtime_directories():
    values = _read_values()
    frontend = (CHART / "templates" / "deployment-frontend.yaml").read_text(encoding="utf-8")
    nginx_template = (ROOT / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")

    assert values["frontend"]["port"] == 8080
    assert "NGINX_PORT" in frontend
    assert "BACKEND_HOST" in frontend
    assert "LOCALFORGE_API_TOKEN" in frontend
    for mount in ("/var/cache/nginx", "/var/run", "/etc/nginx/conf.d", "/var/log/nginx"):
        assert mount in frontend
    assert "listen ${NGINX_PORT}" in nginx_template


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed in this environment")
def test_helm_lint_and_template():
    lint = subprocess.run(["helm", "lint", str(CHART)], capture_output=True, text=True)
    assert lint.returncode == 0, lint.stderr
    rendered = subprocess.run(
        ["helm", "template", "forgeos-test", str(CHART)],
        capture_output=True,
        text=True,
    )
    assert rendered.returncode == 0, rendered.stderr
    assert "kind: NetworkPolicy" in rendered.stdout
    assert "app.kubernetes.io/component: deployment-evidence" in rendered.stdout
    assert "/__forgeos_readiness_failure__" in rendered.stdout


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed in this environment")
def test_helm_template_is_safe_without_deployment_evidence_values():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "forgeos-test",
            str(CHART),
            "--set-json",
            "deploymentEvidence=null",
        ],
        capture_output=True,
        text=True,
    )

    assert rendered.returncode == 0, rendered.stderr
    assert "app.kubernetes.io/component: deployment-evidence" not in rendered.stdout
    assert "name: forgeos-evidence" not in rendered.stdout
    assert 'FORGEOS_EVIDENCE_SCHEMA: "disabled"' in rendered.stdout
    assert 'FORGEOS_EVIDENCE_PATH: "/tmp/forgeos-evidence"' in rendered.stdout
