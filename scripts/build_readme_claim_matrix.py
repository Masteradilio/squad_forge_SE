"""Build the auditable README claim matrix for the full-coverage plan."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "e2e" / "full-coverage"
SCHEMA = "forgeos.readme_claim_matrix.v1"
CLASSIFICATIONS = {"LIVE", "STRUCTURAL", "OPTIONAL", "NOT_PROVEN"}


def evidence(kind: str, path: str, assertion: str) -> dict[str, str]:
    return {"kind": kind, "path": path, "assertion": assertion}


def _claims() -> list[dict[str, Any]]:
    metrics = "docs/e2e/reference/forgeos_reference_metrics.json"
    report = "docs/e2e/reference/forgeos_reference_report.md"
    control_plane = "docs/e2e/reference/control_plane.json"
    return [
        {
            "id": "README-001",
            "section": "Model gateway and economy controls",
            "statement": "Runtime model traffic is routed through the local OmniRoute-compatible endpoint.",
            "classification": "LIVE",
            "evidence": [evidence("execution", metrics, "seven model calls were attributed to OmniRoute")],
            "note": "Observed in the accepted reference run; this does not prove every future deployment configuration.",
        },
        {
            "id": "README-002",
            "section": "Model gateway and economy controls",
            "statement": "Preflight discovers the live catalog and records the selected route and provider evidence.",
            "classification": "LIVE",
            "evidence": [evidence("execution", metrics, "catalog_reachable and structured_probe_passed are true")],
            "note": "Proven for the accepted run against the reachable gateway recorded in the metrics artifact.",
        },
        {
            "id": "README-003",
            "section": "Model gateway and economy controls",
            "statement": "The finite route ladder reports infrastructure blockers instead of disguising failure as product success.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "benchmark status and blocker fields are persisted"),
                evidence("test", "backend/tests/test_llm_provider.py", "provider failure classification and fallback behavior"),
            ],
            "note": "The accepted run proves the reporting boundary; provider failure variants remain unit-tested rather than production-proven.",
        },
        {
            "id": "README-004",
            "section": "Model gateway and economy controls",
            "statement": "Structured Chief Engineer calls use a bounded configurable timeout.",
            "classification": "STRUCTURAL",
            "evidence": [
                evidence("code", "backend/localforge/core/config.py", "bounded omniroute_structured_timeout configuration"),
                evidence("test", "backend/tests/test_core_config.py", "timeout setting is explicit and bounded"),
            ],
            "note": "The configuration contract is proven; a long-running production timeout scenario is not part of the accepted reference run.",
        },
        {
            "id": "README-005",
            "section": "PRD-to-PR evidence pipeline",
            "statement": "The PRD-to-PR pipeline reaches bounded agent turns, tests, repair/review, artifacts, and PR_READY.",
            "classification": "LIVE",
            "evidence": [evidence("execution", metrics, "five imported tasks reached PR_READY and the run completed")],
            "note": "Proven by the accepted ForgeLedger reference execution.",
        },
        {
            "id": "README-006",
            "section": "PRD-to-PR evidence pipeline",
            "statement": "Task contracts constrain files, APIs, tests, dependencies, risk, and required release evidence.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", report, "reference report links task artifacts and acceptance evidence"),
                evidence("test", "backend/tests/test_pr_factory.py", "PR evidence and contract behavior are tested"),
            ],
            "note": "The contract path is observed in the reference run; arbitrary production-scale task shapes are not covered yet.",
        },
        {
            "id": "README-007",
            "section": "Typed Agent Harness",
            "statement": "The shared Harness provides typed methods, bounded strategies, context compaction, schema validation, retries, spans, and tool hooks.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "typed_agent_harness conformance passed"),
                evidence("code", "backend/localforge/runtime/agent_harness.py", "Harness contract and execution boundary"),
            ],
            "note": "Proven for the reference probe and source contract; broad workload coverage remains future work.",
        },
        {
            "id": "README-008",
            "section": "Durable Harness State and subagents",
            "statement": "Harness state and subagent lifecycles persist with parentage, bounds, snapshots, and terminal protection.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "durable_harness_state and bounded_subagents conformance passed"),
                evidence("code", "backend/localforge/runtime/harness_state.py", "atomic state and refinement boundary"),
                evidence("code", "backend/localforge/runtime/subagents.py", "bounded parent-child lifecycle"),
            ],
            "note": "Reference probes prove the bounded lifecycle, not Pod restart recovery.",
        },
        {
            "id": "README-009",
            "section": "Long-running control plane",
            "statement": "Goals, todos, claims, leases, receipts, quotas, signals, and review projections are durable and authoritative.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "control plane completed with five receipts and ten revisions"),
                evidence("execution", control_plane, "goal, todos, receipts, events, and idempotency keys persisted"),
            ],
            "note": "The reference run proves local durable execution; Kubernetes restart and multi-tenant isolation are not proven.",
        },
        {
            "id": "README-010",
            "section": "Skills and engineering workflow",
            "statement": "Built-in and user-created skills are declarative, bounded, selected from task context, and safety-gated.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "skills conformance passed for built-ins and a persisted custom manifest"),
                evidence("code", "backend/localforge/skills/registry.py", "skill selection and manifest validation"),
            ],
            "note": "Proven for the reference skill path; no claim is made about a large community catalog.",
        },
        {
            "id": "README-011",
            "section": "Safety, memory, and observability",
            "statement": "ActionGateway and Safety Kernel enforce role, path, command, network, Git, protected-file, and human-approval boundaries.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "safety_hooks conformance denied a tool before execution"),
                evidence("code", "backend/localforge/safety/hooks.py", "pre-execution safety hook boundary"),
                evidence("test", "backend/tests/test_safety_kernel.py", "safety policy and protected action tests"),
            ],
            "note": "The accepted run proves a denial boundary; the complete human approval journey remains a plan item.",
        },
        {
            "id": "README-012",
            "section": "Safety, memory, and observability",
            "statement": "Graphify, MemPalace, RuleSynthesizer, and OpenTelemetry timeline events provide local evidence and memory boundaries.",
            "classification": "LIVE",
            "evidence": [
                evidence("execution", metrics, "memory and observability conformance passed"),
                evidence("code", "backend/localforge/memory/graphify_engine.py", "local graph construction"),
                evidence("code", "backend/localforge/observability/tracer.py", "nested span and lifecycle event model"),
            ],
            "note": "Proven for local fixtures and reference spans; long-running production telemetry is not proven.",
        },
        {
            "id": "README-013",
            "section": "Safety, memory, and observability",
            "statement": "Context7 MCP is an available optional integration surface for current documentation.",
            "classification": "OPTIONAL",
            "evidence": [
                evidence("live_probe", "scripts/probe_context7.py", "reproducible live probe without printing credentials"),
                evidence("test", "backend/tests/test_context7_mcp.py", "authentication, session, fallback, and audit integration tests"),
            ],
            "note": "The current reference benchmark intentionally does not require Context7; this is not a benchmark-wide LIVE claim.",
        },
        {
            "id": "README-014",
            "section": "Safety, memory, and observability",
            "statement": "Redis cache, pub/sub, and lock primitives are available as an optional integration surface.",
            "classification": "OPTIONAL",
            "evidence": [
                evidence("code", "backend/localforge/services/redis_manager.py", "Redis manager interface"),
                evidence("test", "backend/tests/test_redis_manager.py", "Redis manager contract tests"),
            ],
            "note": "No live Redis server, lock race, pub/sub, or restart evidence is present in the accepted reference run.",
        },
        {
            "id": "README-015",
            "section": "Safety, memory, and observability",
            "statement": "Helm templates and autoscaling are available as an optional deployment surface.",
            "classification": "OPTIONAL",
            "evidence": [
                evidence("code", "deploy/helm/forgeos-cloud/Chart.yaml", "Helm chart metadata"),
                evidence("code", "deploy/helm/forgeos-cloud/templates/hpa-sandbox.yaml", "HPA template"),
            ],
            "note": "The reference run checks only surface presence; helm lint, install, readiness failure, and rollback remain unproven.",
        },
        {
            "id": "README-016",
            "section": "Frontend product boundary",
            "statement": "The frontend exposes mission, task, agent, skill, memory, safety, review, and timeline surfaces.",
            "classification": "STRUCTURAL",
            "evidence": [
                evidence("code", "frontend/src/App.tsx", "frontend route and feature composition"),
                evidence("code", "frontend/src/components/SkillsEditorView.tsx", "feature view implementation"),
            ],
            "note": "Source presence is proven; reproducible build, browser behavior, accessibility, and hosted deployment are not.",
        },
        {
            "id": "README-017",
            "section": "Frontend product boundary",
            "statement": "A frontend build or hosted deployment is a separate release gate.",
            "classification": "NOT_PROVEN",
            "evidence": [
                evidence("docs", "README.md", "README explicitly separates the frontend release gate"),
                evidence("code", "frontend/package.json", "frontend package contract"),
            ],
            "note": "The repository does not yet contain accepted build, browser, and hosted evidence for the full Mission Control journey.",
        },
        {
            "id": "README-018",
            "section": "Clean-room and runtime boundaries",
            "statement": "Reference repositories are not runtime dependencies and source code is not copied into ForgeOS.",
            "classification": "STRUCTURAL",
            "evidence": [
                evidence("docs", "docs/REFERENCE_FEATURE_AUDIT.md", "clean-room adoption boundaries"),
                evidence("code", "pyproject.toml", "declared runtime dependencies"),
            ],
            "note": "Static dependency and documentation evidence exists; a separate release audit should repeat this check.",
        },
        {
            "id": "README-019",
            "section": "Project status and governance",
            "statement": "Human review remains required before merge, deploy, publication, or irreversible external action.",
            "classification": "STRUCTURAL",
            "evidence": [
                evidence("docs", "README.md", "governance statement"),
                evidence("code", "backend/localforge/safety/runner.py", "safety-mediated action execution"),
            ],
            "note": "The control boundary exists, but the full deny/expire/approve UI/API journey is a later plan task.",
        },
    ]


def build_matrix(root: Path = ROOT) -> dict[str, Any]:
    claims = _claims()
    matrix = {
        "schema": SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "repository_root": ".",
        "claims": claims,
    }
    validate_matrix(matrix, root=root)
    counts = Counter(claim["classification"] for claim in claims)
    matrix["summary"] = {
        "total_claims": len(claims),
        "by_classification": {name: counts.get(name, 0) for name in sorted(CLASSIFICATIONS)},
    }
    return matrix


def validate_matrix(matrix: dict[str, Any], root: Path = ROOT) -> None:
    if matrix.get("schema") != SCHEMA:
        raise ValueError("unsupported README claim matrix schema")
    claims = matrix.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("README claim matrix must contain claims")
    ids: set[str] = set()
    for claim in claims:
        claim_id = claim.get("id")
        if not isinstance(claim_id, str) or claim_id in ids:
            raise ValueError(f"duplicate or invalid claim id: {claim_id}")
        ids.add(claim_id)
        if claim.get("classification") not in CLASSIFICATIONS:
            raise ValueError(f"invalid classification for {claim_id}")
        evidence_items = claim.get("evidence")
        if not isinstance(evidence_items, list) or not evidence_items:
            raise ValueError(f"claim {claim_id} has no evidence")
        for item in evidence_items:
            path = item.get("path") if isinstance(item, dict) else None
            if not path or not (root / path).is_file():
                raise ValueError(f"claim {claim_id} references missing evidence: {path}")
            if not item.get("kind") or not item.get("assertion"):
                raise ValueError(f"claim {claim_id} has incomplete evidence metadata")
        if not claim.get("note"):
            raise ValueError(f"claim {claim_id} has no limitation note")


def render_report(matrix: dict[str, Any]) -> str:
    summary = matrix["summary"]
    lines = [
        "# ForgeOS README Claim Matrix",
        "",
        f"- Schema: `{matrix['schema']}`",
        f"- Generated at: `{matrix['generated_at']}`",
        f"- Total claims: **{summary['total_claims']}**",
        "",
        "## Classification summary",
        "",
        "| Classification | Count | Meaning |",
        "| --- | ---: | --- |",
        "| LIVE | %d | Observed in an executable reference or live probe |" % summary["by_classification"]["LIVE"],
        "| STRUCTURAL | %d | Code, contract, or focused test evidence only |" % summary["by_classification"]["STRUCTURAL"],
        "| OPTIONAL | %d | Available surface not required by the reference run |" % summary["by_classification"]["OPTIONAL"],
        "| NOT_PROVEN | %d | Explicit gap preserved for a later gate |" % summary["by_classification"]["NOT_PROVEN"],
        "",
        "## Claim-to-evidence matrix",
        "",
        "| ID | Classification | Claim | Evidence | Limitation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for claim in matrix["claims"]:
        evidence_text = "; ".join(
            f"`{item['kind']}: {item['path']}` — {item['assertion']}"
            for item in claim["evidence"]
        )
        lines.append(
            f"| {claim['id']} | **{claim['classification']}** | {claim['statement']} | "
            f"{evidence_text} | {claim['note']} |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, matrix: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "readme_claim_matrix.json").write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "readme_claim_report.md").write_text(render_report(matrix), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true", help="validate and regenerate the deterministic artifacts")
    args = parser.parse_args()
    matrix = build_matrix()
    write_outputs(args.output_dir, matrix)
    print(json.dumps(matrix["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
