"""Run the auditable ForgeOS full-coverage benchmark.

The runner is deliberately conservative: missing required evidence is recorded
as ``NOT_PROVEN``/``BLOCKED`` and can never become a successful release by
accident.  Destructive Kubernetes operations are never performed implicitly;
the benchmark namespace is created only by an explicit deployment command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - project runtime includes python-dotenv
    dotenv_values = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / ".localforge" / "artifacts" / "full-coverage"


@dataclass
class CommandResult:
    name: str
    command: list[str]
    cwd: str
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    status: str


@dataclass
class GateResult:
    gate: str
    status: str
    evidence: list[str]
    reason: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _redact(text: str) -> str:
    redacted = text
    for name in ("CONTEXT7_API_KEY", "OMNIROUTE_API_KEY", "LOCALFORGE_MODEL_API_KEY"):
        value = os.getenv(name)
        if value and len(value) > 3:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def run_command(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
    timeout_seconds: float = 120.0,
) -> CommandResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        exit_code: int | None = completed.returncode
        stdout = _redact(completed.stdout)
        stderr = _redact(completed.stderr)
        status = "PASS" if completed.returncode == 0 else "FAIL"
    except FileNotFoundError as exc:
        exit_code = None
        stdout = ""
        stderr = str(exc)
        status = "NOT_PROVEN"
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout = _redact((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        stderr = _redact((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        status = "TIMEOUT"
    return CommandResult(
        name=name,
        command=list(command),
        cwd=str(cwd),
        exit_code=exit_code,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout=stdout[-12000:],
        stderr=stderr[-12000:],
        status=status,
    )


def _tool(name: str) -> str | None:
    candidates = [name]
    if sys.platform == "win32" and name in {"npm", "npx"}:
        candidates.insert(0, f"{name}.cmd")
    for candidate in candidates:
        discovered = shutil.which(candidate)
        if discovered:
            return discovered
    if name == "helm" and os.name == "nt":
        candidates = sorted(
            Path(os.getenv("LOCALAPPDATA", ""))
            .glob(r"Microsoft\WinGet\Packages\Helm.Helm_*\windows-amd64\helm.exe")
        )
        if candidates:
            return str(candidates[-1])
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_status(path: Path | None) -> str | None:
    """Read a machine-generated evidence status without trusting file presence."""

    if path is None or not path.is_file():
        return None
    try:
        # Evidence may be emitted by PowerShell tooling with a UTF-8 BOM.
        # Accept both encodings while keeping status validation fail-closed.
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _load_workspace_env() -> None:
    """Load workspace-local benchmark credentials without persisting them."""

    env_path = ROOT / ".env"
    if not env_path.is_file() or dotenv_values is None:
        return
    for key, value in dotenv_values(env_path).items():
        if key and value is not None:
            os.environ.setdefault(key, value)


def _gate(gate: str, status: str, evidence: list[str], reason: str) -> GateResult:
    return GateResult(gate=gate, status=status, evidence=evidence, reason=reason)


def _render_report(
    *,
    run_id: str,
    gates: list[GateResult],
    commands: list[CommandResult],
) -> str:
    overall = "ACCEPTED" if all(item.status == "PASS" for item in gates) else "PARTIAL"
    lines = [
        "# ForgeOS — Relatório de conformidade de cobertura completa",
        "",
        f"- Run ID: `{run_id}`",
        f"- Gerado em: `{_now()}`",
        f"- Veredito: **{overall}**",
        "",
        "> Ausência de evidência obrigatória permanece explícita; este relatório não converte código estrutural em PASS.",
        "",
        "## Gates PA-001 a PA-014",
        "",
        "| Gate | Status | Motivo | Evidências |",
        "| --- | --- | --- | --- |",
    ]
    for item in gates:
        evidence = "; ".join(f"`{path}`" for path in item.evidence) or "—"
        lines.append(f"| {item.gate} | **{item.status}** | {item.reason} | {evidence} |")
    lines.extend(["", "## Comandos executados", "", "| Nome | Status | Exit | Duração (s) |", "| --- | --- | ---: | ---: |"])
    for item in commands:
        lines.append(
            f"| `{item.name}` | **{item.status}** | {item.exit_code if item.exit_code is not None else '—'} | {item.duration_seconds:.3f} |"
        )
    lines.extend(["", "## Critério de liberação", "", "`ACCEPTED` exige PASS em todos os gates PA-001..PA-014. Qualquer `NOT_PROVEN`, `TIMEOUT`, `FAIL` ou `BLOCKED` mantém o resultado como `PARTIAL`.", ""])
    return "\n".join(lines)


def run_benchmark(
    output_root: Path,
    *,
    run_id: str,
    skip_frontend: bool = False,
    apply_kubernetes_profile: bool = False,
) -> int:
    _load_workspace_env()
    benchmark_project_id = os.getenv("FORGEOS_BENCHMARK_PROJECT_ID", "1")
    run_dir = output_root / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    commands: list[CommandResult] = []

    matrix_dir = run_dir / "readme"
    matrix = run_command(
        "PA-001-readme-matrix",
        [sys.executable, "scripts/build_readme_claim_matrix.py", "--output-dir", str(matrix_dir)],
    )
    commands.append(matrix)

    profile_dir = run_dir / "kubernetes-profile"
    profile = run_command(
        "PA-002-kubernetes-profile",
        [
            sys.executable,
            "scripts/generate_benchmark_k8s_profile.py",
            "--run-id",
            run_id,
            "--output-dir",
            str(profile_dir),
            "--project-id",
            benchmark_project_id,
        ],
    )
    commands.append(profile)

    profile_compliance: CommandResult | None = None
    if apply_kubernetes_profile and _tool("kubectl"):
        profile_compliance = run_command(
            "PA-002-kubernetes-profile-live",
            [
                sys.executable,
                "scripts/run_kubernetes_profile_compliance.py",
                "--run-id",
                run_id,
                "--output-dir",
                str(run_dir / "kubernetes-profile-live"),
                "--context",
                os.getenv("FORGEOS_KUBERNETES_CONTEXT", "docker-desktop"),
                "--runner-image",
                os.getenv("FORGEOS_BENCHMARK_RUNNER_IMAGE", "local_forge_os-backend:latest"),
                "--project-id",
                benchmark_project_id,
                "--apply",
                "--bootstrap-runtime-secret",
                "--wait-seconds",
                os.getenv("FORGEOS_KUBERNETES_PROFILE_WAIT_SECONDS", "900"),
                "--poll-seconds",
                os.getenv("FORGEOS_KUBERNETES_PROFILE_POLL_SECONDS", "5"),
            ],
            timeout_seconds=1200,
        )
        commands.append(profile_compliance)

    context7 = run_command(
        "PA-003-context7-live-probe",
        [sys.executable, "scripts/probe_context7.py"],
        timeout_seconds=60,
    )
    commands.append(context7)
    if context7.stdout:
        (run_dir / "context7_probe.json").write_text(context7.stdout + "\n", encoding="utf-8")

    context7_task = run_command(
        "PA-003-context7-task-decision",
        [
            sys.executable,
            "scripts/run_context7_compliance.py",
            "--output",
            str(run_dir / "context7-decision"),
        ],
        timeout_seconds=120,
    )
    commands.append(context7_task)

    redis_url = os.getenv("FORGEOS_REDIS_URL") or os.getenv("REDIS_URL")
    if redis_url:
        redis = run_command(
            "PA-004-redis-probe",
            [sys.executable, "scripts/probe_redis.py", "--url", redis_url, "--output", str(run_dir / "redis_probe.json")],
            timeout_seconds=60,
        )
    elif _tool("kubectl"):
        redis = run_command(
            "PA-004-redis-probe",
            [
                sys.executable,
                "scripts/run_kubernetes_redis_probe.py",
                "--output",
                str(run_dir / "redis_probe.json"),
            ],
            timeout_seconds=180,
        )
    else:
        redis = CommandResult("PA-004-redis-probe", [], str(ROOT), None, 0.0, "", "FORGEOS_REDIS_URL/REDIS_URL not configured", "NOT_PROVEN")
    commands.append(redis)

    helm_path = _tool("helm")
    if helm_path:
        commands.append(run_command("PA-005-helm-lint", [helm_path, "lint", "deploy/helm/forgeos-cloud"]))
        commands.append(run_command("PA-005-helm-template", [helm_path, "template", "forgeos-compliance", "deploy/helm/forgeos-cloud"]))
    else:
        commands.append(CommandResult("PA-005-helm", [], str(ROOT), None, 0.0, "", "helm not found", "NOT_PROVEN"))

    kubectl_path = _tool("kubectl")
    if kubectl_path:
        commands.append(run_command("PA-005-kubernetes-pods", [kubectl_path, "get", "pods", "-n", "forgeos", "-o", "json"], timeout_seconds=30))
        commands.append(run_command("PA-005-kubernetes-services", [kubectl_path, "get", "services", "-n", "forgeos", "-o", "json"], timeout_seconds=30))
        commands.append(
            run_command(
                "PA-010-recovery-kubernetes",
                [
                    sys.executable,
                    "scripts/run_kubernetes_recovery_compliance.py",
                    "--output",
                    str(run_dir / "recovery" / "kubernetes_recovery.json"),
                    "--run-id",
                    run_id,
                ],
                timeout_seconds=360,
            )
        )
    else:
        commands.append(CommandResult("PA-005-kubectl", [], str(ROOT), None, 0.0, "", "kubectl not found", "NOT_PROVEN"))

    if not skip_frontend:
        npm_path = _tool("npm") or "npm"
        npx_path = _tool("npx") or "npx"
        for name, command in (
            ("PA-006-frontend-lint", [npm_path, "run", "lint"]),
            ("PA-006-frontend-typecheck", [npx_path, "tsc", "-p", "tsconfig.app.json", "--noEmit"]),
            ("PA-006-frontend-tests", [npm_path, "test", "--", "--run"]),
            ("PA-006-frontend-build", [npm_path, "run", "build"]),
        ):
            commands.append(run_command(name, command, cwd=ROOT / "frontend", timeout_seconds=180))

    tenancy = run_command(
        "PA-008-tenant-isolation",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "backend/tests/test_tenant_isolation.py",
            f"--junitxml={run_dir / 'tenancy' / 'pytest.xml'}",
        ],
        timeout_seconds=180,
    )
    commands.append(tenancy)

    approval = run_command(
        "PA-009-approval-contract",
        [
            sys.executable,
            "scripts/run_approval_compliance.py",
            "--output",
            str(run_dir / "approval"),
        ],
        timeout_seconds=180,
    )
    commands.append(approval)

    approval_ui = run_command(
        "PA-009-approval-ui",
        [
            _tool("npx") or "npx",
            "vitest",
            "run",
            "src/components/MissionControlView.test.tsx",
        ],
        cwd=ROOT / "frontend",
        timeout_seconds=180,
    )
    commands.append(approval_ui)

    recovery = run_command(
        "PA-010-recovery-fixture",
        [sys.executable, "scripts/run_recovery_compliance.py", "--output", str(run_dir / "recovery")],
        timeout_seconds=120,
    )
    commands.append(recovery)

    ci_pr = run_command(
        "PA-011-ci-pr-fixture",
        [sys.executable, "scripts/run_ci_pr_compliance.py", "--output", str(run_dir / "ci-pr")],
        timeout_seconds=120,
    )
    commands.append(ci_pr)

    security = run_command(
        "PA-012-security-audit",
        [
            sys.executable,
            "scripts/run_security_audit.py",
            "--output",
            str(run_dir / "security" / "security_audit.json"),
        ],
        timeout_seconds=360,
    )
    commands.append(security)

    playwright_command = os.getenv("FORGEOS_PLAYWRIGHT_COMMAND")
    if playwright_command:
        commands.append(run_command("PA-007-playwright", ["powershell", "-NoProfile", "-Command", playwright_command], timeout_seconds=600))
    elif kubectl_path:
        commands.append(
            run_command(
                "PA-007-playwright",
                [
                    sys.executable,
                    "scripts/run_playwright_cluster_compliance.py",
                    "--artifact-dir",
                    str(run_dir / "playwright"),
                ],
                timeout_seconds=900,
            )
        )
    load_command = os.getenv("FORGEOS_LOAD_COMMAND")
    if load_command:
        commands.append(run_command("PA-013-load", ["powershell", "-NoProfile", "-Command", load_command], timeout_seconds=600))
    elif kubectl_path:
        commands.append(
            run_command(
                "PA-013-load",
                [
                    sys.executable,
                    "scripts/run_kubernetes_load_probe.py",
                    "--output",
                    str(run_dir / "load" / "kubernetes_load_compliance.json"),
                ],
                timeout_seconds=360,
            )
        )

    redis_recovery_source = os.getenv("FORGEOS_REDIS_RECOVERY_EVIDENCE")
    if redis_recovery_source and Path(redis_recovery_source).is_file():
        shutil.copy2(redis_recovery_source, run_dir / "redis_recovery.json")

    benchmark_pod_source = os.getenv("FORGEOS_BENCHMARK_POD_EVIDENCE")
    if benchmark_pod_source and Path(benchmark_pod_source).is_file():
        shutil.copy2(benchmark_pod_source, run_dir / "benchmark_pod_evidence.json")
    elif profile_compliance is not None:
        live_profile_report = run_dir / "kubernetes-profile-live" / "compliance-report.json"
        if live_profile_report.is_file():
            shutil.copy2(live_profile_report, run_dir / "benchmark_pod_evidence.json")

    rollout_source = os.getenv("FORGEOS_ROLLOUT_EVIDENCE")
    if rollout_source and Path(rollout_source).is_file():
        shutil.copy2(rollout_source, run_dir / "helm_rollout_evidence.json")

    command_by_name = {item.name: item for item in commands}
    profile_manifest = profile_dir / "manifest.yaml"
    benchmark_pod_evidence = run_dir / "benchmark_pod_evidence.json"
    rollout_evidence = run_dir / "helm_rollout_evidence.json"
    playwright_evidence = run_dir / "playwright" / "run-manifest.json"
    gates = [
        _gate("PA-001", "PASS" if matrix.status == "PASS" else "BLOCKED", [str(matrix_dir / "readme_claim_matrix.json")], "matriz gerada e validada" if matrix.status == "PASS" else "matriz não foi gerada"),
        _gate("PA-002", "PASS" if profile.status == "PASS" and profile_manifest.is_file() and _artifact_status(benchmark_pod_evidence) == "PASS" else "PARTIAL", [str(profile_manifest), str(benchmark_pod_evidence)], "perfil e execução do Pod comprovados" if _artifact_status(benchmark_pod_evidence) == "PASS" else "perfil Kubernetes renderizado; execução do benchmark no Pod ainda não foi comprovada"),
        _gate("PA-003", "PASS" if context7.status == "PASS" and (run_dir / "context7_decision.json").is_file() else ("PARTIAL" if context7.status == "PASS" else "NOT_PROVEN"), [str(run_dir / "context7_probe.json"), str(run_dir / "context7_decision.json")], "probe live e decisão de tarefa vinculada" if (run_dir / "context7_decision.json").is_file() else "probe live disponível; decisão de tarefa ainda precisa estar vinculada"),
        _gate("PA-004", "PASS" if redis.status == "PASS" and (run_dir / "redis_recovery.json").is_file() else ("PARTIAL" if redis.status == "PASS" else "NOT_PROVEN"), [str(run_dir / "redis_probe.json"), str(run_dir / "redis_recovery.json")], "Redis, recovery e fail-closed comprovados" if (run_dir / "redis_recovery.json").is_file() else ("probe Redis executado; recovery/fail-closed ainda não foi comprovado" if redis.status == "PASS" else "Redis live não foi configurado")),
        _gate("PA-005", "PASS" if command_by_name.get("PA-005-helm-lint", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS" and command_by_name.get("PA-005-helm-template", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS" and kubectl_path and _artifact_status(rollout_evidence) == "PASS" else "PARTIAL", ["deploy/helm/forgeos-cloud", str(rollout_evidence)], "chart, cluster, readiness failure e rollback comprovados" if _artifact_status(rollout_evidence) == "PASS" else "chart e cluster respondem; readiness failure/rollback ainda devem ser evidenciados"),
        _gate("PA-006", "PASS" if not skip_frontend and all(command_by_name.get(name, CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS" for name in ("PA-006-frontend-lint", "PA-006-frontend-typecheck", "PA-006-frontend-tests", "PA-006-frontend-build")) else "NOT_PROVEN", ["frontend/dist"], "build, lint, typecheck e testes passaram" if not skip_frontend else "frontend foi omitido"),
        _gate("PA-007", "PASS" if command_by_name.get("PA-007-playwright", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS" and _artifact_status(playwright_evidence) == "PASS" else "NOT_PROVEN", [str(playwright_evidence)], "suíte Playwright executada contra o frontend/backend live" if _artifact_status(playwright_evidence) == "PASS" else "evidência Playwright live ausente ou incompleta"),
        _gate("PA-008", "NOT_PROVEN", [], "isolamento multi-tenant precisa de evidência de dois tenants e acessos cruzados"),
        _gate("PA-009", "NOT_PROVEN", [], "jornada API/CLI/UI de aprovação ainda não foi executada pelo runner"),
        _gate("PA-010", "NOT_PROVEN", [], "reinício real de Pod executor ainda não foi executado pelo runner"),
        _gate("PA-011", "NOT_PROVEN", [], "simulador CI/PR externo ainda não foi executado pelo runner"),
        _gate("PA-012", "NOT_PROVEN", [], "scanner SAST/DAST/SCA/imagem/secret ainda não está integrado ao runner"),
        _gate("PA-013", "PASS" if command_by_name.get("PA-013-load", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS" else "NOT_PROVEN", ["FORGEOS_LOAD_COMMAND"], "carga controlada executada" if load_command else "nenhum comando de carga foi fornecido"),
    ]
    # Replace the conservative placeholders for checks that now have local,
    # deterministic evidence runners.  The remaining gates stay fail-closed.
    gates[2] = _gate(
        "PA-003",
        "PASS" if context7.status == "PASS" and context7_task.status == "PASS" else "PARTIAL",
        [str(run_dir / "context7_probe.json"), str(run_dir / "context7-decision" / "context7_decision.json")],
        "Context7 live probe and task decision evidence are linked"
        if context7.status == "PASS" and context7_task.status == "PASS"
        else "Context7 live or task decision evidence is incomplete",
    )
    gates[3] = _gate(
        "PA-004",
        "PASS"
        if redis.status == "PASS" and (run_dir / "redis_recovery.json").is_file()
        else ("PARTIAL" if redis.status == "PASS" else "NOT_PROVEN"),
        [str(run_dir / "redis_probe.json"), str(run_dir / "redis_recovery.json")],
        "Redis capability and post-restart recovery evidence are linked"
        if redis.status == "PASS" and (run_dir / "redis_recovery.json").is_file()
        else "Redis capability passed but controlled restart evidence is missing"
        if redis.status == "PASS"
        else "Redis live probe did not pass",
    )
    gates[1] = _gate(
        "PA-002",
        "PASS"
        if profile.status == "PASS" and profile_manifest.is_file() and _artifact_status(benchmark_pod_evidence) == "PASS"
        else "PARTIAL",
        [str(profile_manifest), str(benchmark_pod_evidence)],
        "profile and real unprivileged benchmark Pod evidence are linked"
        if _artifact_status(benchmark_pod_evidence) == "PASS"
        else "profile rendered; real benchmark Pod evidence is missing or did not pass",
    )
    gates[4] = _gate(
        "PA-005",
        "PASS"
        if all(
            command_by_name.get(name, CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS"
            for name in (
                "PA-005-helm-lint",
                "PA-005-helm-template",
                "PA-005-kubernetes-pods",
                "PA-005-kubernetes-services",
            )
        )
        and _artifact_status(rollout_evidence) == "PASS"
        else "PARTIAL",
        ["deploy/helm/forgeos-cloud", str(rollout_evidence)],
        "chart, live cluster, readiness failure, and rollback evidence are linked"
        if _artifact_status(rollout_evidence) == "PASS"
        else "Helm/cluster checks ran, but valid readiness failure and rollback evidence is missing",
    )
    gates[6] = _gate(
        "PA-007",
        "PASS"
        if command_by_name.get("PA-007-playwright", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS"
        and _artifact_status(playwright_evidence) == "PASS"
        else "NOT_PROVEN",
        [str(playwright_evidence)],
        "desktop/mobile Playwright journey passed against the live Kubernetes service"
        if _artifact_status(playwright_evidence) == "PASS"
        else "live Playwright evidence is missing or did not pass",
    )
    gates[7] = _gate(
        "PA-008",
        "PASS" if tenancy.status == "PASS" else "PARTIAL",
        [str(run_dir / "tenancy" / "pytest.xml")],
        "tenant isolation by API and services is evidenced"
        if tenancy.status == "PASS"
        else "tenant isolation test did not pass",
    )
    gates[8] = _gate(
        "PA-009",
        "PASS" if approval.status == "PASS" and approval_ui.status == "PASS" else "PARTIAL",
        [str(run_dir / "approval" / "approval_compliance.json"), "frontend/src/components/MissionControlView.test.tsx"],
        "API/CLI approval contract and UI decision states are evidenced"
        if approval.status == "PASS" and approval_ui.status == "PASS"
        else "approval API/CLI or UI evidence did not pass",
    )
    gates[9] = _gate(
        "PA-010",
        "PASS"
        if command_by_name.get("PA-010-recovery-kubernetes", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")).status == "PASS"
        and _artifact_status(run_dir / "recovery" / "kubernetes_recovery.json") == "PASS"
        else ("PARTIAL" if recovery.status == "PASS" else "NOT_PROVEN"),
        [str(run_dir / "recovery" / "kubernetes_recovery.json"), str(run_dir / "recovery" / "recovery_compliance.json")],
        "real Pod restart, expired lease, goal identity, single receipt, and idempotent recovery are evidenced"
        if _artifact_status(run_dir / "recovery" / "kubernetes_recovery.json") == "PASS"
        else "local recovery semantics passed but real Kubernetes Pod recovery is missing or did not pass",
    )
    gates[10] = _gate(
        "PA-011",
        "PASS" if ci_pr.status == "PASS" else "PARTIAL",
        [str(run_dir / "ci-pr" / "ci_pr_compliance.json")],
        "signed ordered CI and human boundary are evidenced"
        if ci_pr.status == "PASS"
        else "CI/PR fixture did not pass",
    )
    gates[11] = _gate(
        "PA-012",
        "PASS" if security.status == "PASS" else "PARTIAL",
        [str(run_dir / "security" / "security_audit.json")],
        "security audit passed" if security.status == "PASS" else "security audit remains partial",
    )
    load_result = command_by_name.get(
        "PA-013-load", CommandResult("", [], "", None, 0, "", "", "NOT_PROVEN")
    )
    gates[12] = _gate(
        "PA-013",
        "PASS" if load_result.status == "PASS" else "PARTIAL",
        [str(run_dir / "load" / "kubernetes_load_compliance.json")],
        "small, medium, sustained, and dependency-failure load evidence passed"
        if load_result.status == "PASS"
        else "load or dependency-failure evidence is incomplete",
    )

    gates.append(
        _gate(
            "PA-014",
            "PASS" if all(item.status == "PASS" for item in gates) else "PARTIAL",
            [str(run_dir)],
            "pacote unificado gerado; permanece parcial enquanto algum gate obrigatório não for PASS",
        )
    )

    files = [path for path in run_dir.rglob("*") if path.is_file()]
    manifest = {
        "schema": "forgeos.full_coverage_manifest.v1",
        "run_id": run_id,
        "created_at": _now(),
        "status": "ACCEPTED" if all(item.status == "PASS" for item in gates) else "PARTIAL",
        "gates": [asdict(item) for item in gates],
        "commands": [asdict(item) for item in commands],
        "artifacts": {str(path.relative_to(run_dir)): _sha256(path) for path in files},
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "metrics.json", {"run_id": run_id, "status": manifest["status"], "gates": [asdict(item) for item in gates]})
    (run_dir / "relatorio_conformidade_total.md").write_text(_render_report(run_id=run_id, gates=gates, commands=commands), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "status": manifest["status"], "output": str(run_dir)}, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "ACCEPTED" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument(
        "--apply-kubernetes-profile",
        action="store_true",
        help="run the generated profile in a temporary namespace and require a succeeded Pod",
    )
    args = parser.parse_args()
    return run_benchmark(
        args.output_root,
        run_id=args.run_id,
        skip_frontend=args.skip_frontend,
        apply_kubernetes_profile=args.apply_kubernetes_profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
