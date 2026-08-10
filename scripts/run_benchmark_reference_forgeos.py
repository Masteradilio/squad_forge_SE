"""Run the auditable ForgeOS reference PRD through the real pipeline.

The runner owns benchmark setup, independent acceptance, and evidence reporting.
It never edits generated product source or tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import run_benchmark_v7_mini_prd as base
from localforge.connectors.context7_mcp import Context7MCPConnector
from localforge.memory.graphify_engine import GraphifyEngine
from localforge.memory.mempalace_service import MemPalaceService
from localforge.memory.rule_synthesizer import RuleSynthesizer
from localforge.observability.tracer import OpenTelemetryTracer
from localforge.runtime.agent_harness import AgentHarness, ContextBlock, compact_context
from localforge.runtime.harness_state import HarnessEntry, HarnessState
from localforge.runtime.subagents import (
    HarnessStateSubagentStore,
    SubagentRegistry,
    SubagentSpec,
)
from localforge.safety.hooks import FunctionalToolPolicy, ToolCall, ToolPolicyDecision, ToolPolicyDenied
from localforge.services.redis_manager import RedisManager
from localforge.skills.executor import SkillExecutionContext, SkillExecutor
from localforge.skills.registry import SkillDefinition, SkillRegistry

RUN_SUFFIX = base.datetime.now(base.UTC).strftime("%Y%m%dT%H%M%S%fZ")
base.WORKSPACE = ROOT / "benchmarks" / "workspaces" / f"reference-forgeos-{RUN_SUFFIX}"
base.PRD = ROOT / "docs" / "PRD_REFERENCE_FORGEOS.md"
base.EVIDENCE = ROOT / "docs" / "e2e" / "reference" / f"run-{RUN_SUFFIX}"
base.EXPECTED_TASKS = 5
base.BENCHMARK_LABEL = "ForgeOS Reference ForgeLedger PRD Benchmark"
base.METRICS_FILENAME = "forgeos_reference_metrics.json"
base.REPORT_FILENAME = "forgeos_reference_report.md"
LATEST_EVIDENCE = ROOT / "docs" / "e2e" / "reference"

FIXTURES = [
    ROOT / "scripts" / "fixtures" / "reference_forgeos_create_acceptance.py",
    ROOT / "scripts" / "fixtures" / "reference_forgeos_validation_acceptance.py",
    ROOT / "scripts" / "fixtures" / "reference_forgeos_summary_acceptance.py",
    ROOT / "scripts" / "fixtures" / "reference_forgeos_snapshot_acceptance.py",
]
_REFERENCE_FREE_ROUTE_SELECTOR = base.cloud._explicit_free_routes


def _select_reference_routes(models: list[str]) -> list[str]:
    routes = _REFERENCE_FREE_ROUTE_SELECTOR(models)
    configured = (
        os.environ.get("LOCALFORGE_DEFAULT_MODEL")
        or base.cloud.root_env_values().get("LOCALFORGE_DEFAULT_MODEL")
    )
    benchmark_ladder = [
        route.strip()
        for route in os.environ.get("LOCALFORGE_BENCHMARK_ROUTE_LADDER", "").split(",")
        if route.strip() and route.strip() in models
    ]
    if configured and configured in models:
        benchmark_ladder.insert(0, configured)
    return list(dict.fromkeys([*benchmark_ladder, *routes]))


def _apply_contracts(database: Path) -> dict[str, int]:
    summary = {"chief_only": 0, "chief_led": 0, "local_assisted": 0}
    product_files = ["app/forge_ledger.py"]
    test_targets = [
        "tests/test_forge_ledger_create.py",
        "tests/test_forge_ledger_validation.py",
        "tests/test_forge_ledger_summary.py",
        "tests/test_forge_ledger_snapshot.py",
    ]
    evidence_files = [
        "docs/pr.md",
        "docs/cost_benchmark.md",
        "docs/review.md",
        "docs/risk.md",
    ]
    release_allowed_files = [*evidence_files, "docs/release_manifest.md"]
    required_public_apis = [
        "LedgerStore",
        "add_entry",
        "list_entries",
        "close_entry",
        "summarize",
        "export_snapshot",
    ]
    acceptance_by_index = [
        [
            "add_entry rejects blank labels and creates positive stable integer ids",
            "created entries include the supplied label, amount, closed=False, and a non-empty ISO-8601 created_at",
            "list_entries preserves creation order after reopening the same JSON file",
        ],
        [
            "add_entry rejects non-positive amounts, booleans, and non-integer values",
            "close_entry changes only the selected entry and persists closed=True after reopening",
            "an unknown identifier, including 'missing', raises KeyError",
        ],
        [
            "summarize returns deterministic total_entries, open_entries, closed_entries, and total_amount",
            "summarize does not rewrite or mutate the JSON store",
        ],
        [
            "export_snapshot returns ordered entries and the summary as a JSON-serializable object",
            "export_snapshot does not rewrite or mutate the JSON store",
        ],
    ]
    behaviors = [
        ["LedgerStore persists entries", "add_entry returns stable ids", "list_entries preserves order after reopen"],
        ["blank labels and invalid amounts raise ValueError", "close_entry changes one entry", "unknown ids raise KeyError", "closed state survives reopen"],
        ["summarize returns deterministic counts and amount", "summarize does not mutate JSON"],
        ["export_snapshot contains real ordered entries and summary", "export_snapshot does not mutate JSON"],
    ]
    seniority_by_index = ["local_assisted", "chief_led", "chief_only", "chief_only", "chief_only"]
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, title, description, metadata_json FROM tasks ORDER BY id"
        ).fetchall()
        if len(rows) != base.EXPECTED_TASKS:
            raise RuntimeError(f"reference PRD imported {len(rows)} tasks, expected {base.EXPECTED_TASKS}")
        task_ids = [int(row[0]) for row in rows]
        for index, (task_id, title, description, metadata_raw) in enumerate(rows):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            is_release = index == len(rows) - 1
            if is_release:
                title = "Release assembly: ForgeLedger reference evidence"
                description = "Run all ForgeLedger tests and publish the release manifest while preserving accumulated behavior. Use to-tickets and tdd evidence."
                acceptance = [
                    "All four canonical test modules exist and pass",
                    "docs/release_manifest.md names app/forge_ledger.py",
                    "docs/release_manifest.md names tests/ and python -m pytest tests -q",
                ]
                connection.execute(
                    "UPDATE tasks SET title = ?, description = ?, acceptance_criteria = ? WHERE id = ?",
                    (title, description, json.dumps(acceptance), task_id),
                )
            else:
                acceptance = acceptance_by_index[index]
                connection.execute(
                    "UPDATE tasks SET acceptance_criteria = ? WHERE id = ?",
                    (json.dumps(acceptance), task_id),
                )
            seniority = seniority_by_index[index]
            task_allowed_files = release_allowed_files if is_release else [
                *product_files,
                test_targets[index],
            ]
            if is_release:
                # The compiler adds a generic HTML integration task to every
                # plan. This benchmark's release task is deliberately a
                # Python evidence assembly task, so remove that stale marker
                # and replace its sizing projection before the scheduler runs.
                metadata.pop("is_integration_task", None)
                metadata["reference_benchmark_release"] = True
                metadata["sizing"] = {
                    "needs_split": False,
                    "risk_level": "medium",
                    "reasons": [],
                    "acceptance_criteria": acceptance,
                }
            metadata["task_contract"] = {
                "allowed_files": task_allowed_files,
                # Every incremental task reruns the accumulated suite. This
                # prevents a later feature from replacing an already accepted
                # public API while still passing only its new fixture.
                "canonical_test_command": "python -m pytest tests -q",
                "seniority_class": seniority,
                "visual_required": False,
                "acceptance_test_policy": "observable_behavior_only",
                "acceptance_behaviors": sum(behaviors, []) if is_release else behaviors[index],
                # The release task is intentionally documentation-only; the
                # accumulated product API is verified by the full-suite and
                # independent acceptance gates, not by a docs-only diff.
                "required_public_apis": [] if is_release else required_public_apis,
                "forbidden_dependencies": ["third-party runtime dependencies"],
                "acceptance_test_fixture_source": str(FIXTURES[index]) if not is_release else None,
                "acceptance_test_fixture_target": test_targets[index] if not is_release else None,
                "required_product_files": product_files,
                "required_artifact": (
                    {"path": "docs/release_manifest.md", "markers": ["app/forge_ledger.py", "tests/", "python -m pytest tests -q"]}
                    if is_release else None
                ),
                "required_skills": ["grill-with-docs", "to-tickets", "tdd"],
                "implementation_notes": [
                    "Use the exact public API in PRD_REFERENCE_FORGEOS.md.",
                    "Acceptance must import and execute app/forge_ledger.py.",
                    "Do not duplicate the product algorithm inside tests.",
                    "Keep JSON persistence stable and preserve all prior behavior.",
                    "An unknown non-numeric id must raise KeyError, not ValueError.",
                    "Do not add third-party runtime dependencies.",
                    "Preserve every previously accepted public API and behavior; run the full accumulated test suite before declaring readiness.",
                    "Keep the exact amount field and module-level function names from PRD_REFERENCE_FORGEOS.md; do not rename amount to minutes or replace functions with methods.",
                    "Do not use pytest.skip, xfail, importorskip, or placeholder assertions.",
                    "The release task adds docs/release_manifest.md without rewriting a passing module.",
                ],
                "reference_benchmark": True,
                "source_title": str(title),
                "source_description": str(description),
            }
            connection.execute(
                "UPDATE tasks SET dependency_task_ids = ?, risk_level = ?, metadata_json = ? WHERE id = ?",
                (
                    json.dumps([] if index == 0 else [task_ids[index - 1]]),
                    "low" if seniority == "local_assisted" else "medium",
                    json.dumps(metadata),
                    task_id,
                ),
            )
            summary[seniority] += 1
        connection.commit()
    return summary


base._apply_contracts = _apply_contracts


def _artifact_types(database: Path) -> dict[str, int]:
    with sqlite3.connect(database) as connection:
        return {
            str(kind): int(count)
            for kind, count in connection.execute(
                "SELECT type, COUNT(*) FROM artifacts GROUP BY type"
            ).fetchall()
        }
def _final_acceptance() -> dict[str, Any]:
    worktree = base.WORKSPACE / ".localforge" / "worktrees" / "lf-prd-005"
    if not worktree.is_dir():
        return {"passed": False, "reason": "release worktree is missing", "commands": []}
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(worktree)
    environment["DEEPEVAL_DISABLE_DOTENV"] = "1"
    commands: list[dict[str, Any]] = []
    for command in (
        [sys.executable, "-m", "pytest", "tests", "-q"],
        [sys.executable, "-m", "pytest", *[str(path) for path in FIXTURES], "-q"],
    ):
        completed = subprocess.run(
            command,
            cwd=worktree,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        commands.append(
            {
                "command": command[2:],
                "exit_code": completed.returncode,
                "stdout_tail": (completed.stdout or "")[-1600:],
                "stderr_tail": (completed.stderr or "")[-1600:],
            }
        )
    manifest = worktree / "docs" / "release_manifest.md"
    manifest_text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    markers = ("app/forge_ledger.py", "tests/", "python -m pytest tests -q")
    manifest_ok = all(marker in manifest_text for marker in markers)
    return {
        "passed": all(item["exit_code"] == 0 for item in commands) and manifest_ok,
        "manifest_ok": manifest_ok,
        "commands": commands,
    }


def _control_plane_snapshot() -> tuple[dict[str, Any] | None, str | None]:
    directory = base.WORKSPACE / ".localforge" / "control_plane"
    states = sorted(
        [*directory.glob("run-*.json"), *directory.glob("goal-*.json")],
        key=lambda path: path.stat().st_mtime,
    )
    events = sorted(
        [*directory.glob("run-*.events.jsonl"), *directory.glob("goal-*.events.jsonl")],
        key=lambda path: path.stat().st_mtime,
    )
    state = json.loads(states[-1].read_text(encoding="utf-8")) if states else None
    event_text = events[-1].read_text(encoding="utf-8") if events else None
    return state, event_text


def _conformance(
    metrics: dict[str, Any],
    final: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    artifacts: dict[str, int],
) -> dict[str, dict[str, Any]]:
    sqlite_metrics = metrics.get("sqlite", {})
    gateway = metrics.get("gateway", {})
    control_plane = metrics.get("control_plane", {})
    required_artifacts = {
        "PlanArtifact",
        "DiffArtifact",
        "TestArtifact",
        "ReviewArtifact",
        "RiskArtifact",
        "PRArtifact",
    }
    provider_ok = (
        sqlite_metrics.get("model_calls_logged", 0) > 0
        and set(sqlite_metrics.get("calls_by_provider", {})) == {"omniroute"}
    )
    return {
        "omniroute_gateway": {
            "status": "PASS"
            if gateway.get("catalog_reachable")
            and gateway.get("structured_probe_passed")
            and provider_ok
            else "FAIL",
            "evidence": f"route={gateway.get('selected_route')}; providers={sqlite_metrics.get('calls_by_provider')}",
        },
        "prd_pipeline": {
            "status": "PASS"
            if sqlite_metrics.get("task_statuses", {}).get("PR_READY") == base.EXPECTED_TASKS
            and metrics.get("status") == "ACCEPTED"
            else "FAIL",
            "evidence": f"tasks={sqlite_metrics.get('task_statuses')}; runs={sqlite_metrics.get('runs')}",
        },
        "control_plane": {
            "status": "PASS" if control_plane.get("completed") else "FAIL",
            "evidence": f"revision={control_plane.get('revision')}; receipts={control_plane.get('receipts')}; events={control_plane.get('events')}",
        },
        "independent_acceptance": {
            "status": "PASS" if final.get("passed") else "FAIL",
            "evidence": json.dumps(
                {
                    "manifest_ok": final.get("manifest_ok"),
                    "commands": [
                        {"exit_code": item.get("exit_code"), "command": item.get("command")}
                        for item in final.get("commands", [])
                    ],
                }
            ),
        },
        "artifacts": {
            "status": "PASS" if required_artifacts.issubset(artifacts) else "FAIL",
            "evidence": f"required={sorted(required_artifacts)}; observed={artifacts}",
        },
        **probes,
    }


def _write_report(
    metrics: dict[str, Any],
    conformance: dict[str, dict[str, Any]],
    control_plane: dict[str, Any] | None,
) -> None:
    labels = {
        "omniroute_gateway": "OmniRoute-only live gateway and model evidence",
        "prd_pipeline": "PRD import, contracts, worktrees, tasks, and PR_READY",
        "typed_agent_harness": "Typed Predict/CodeAct-style Harness contract",
        "durable_harness_state": "Durable prompts, memory, refinement, snapshots",
        "bounded_subagents": "Bounded parent/child subagent lifecycle",
        "control_plane": "Lifetime goal, receipts, quota/frontier, and events",
        "skills": "Built-in and persisted custom skills",
        "safety_hooks": "Pre-execution safety hook boundary",
        "observability": "Nested spans and lifecycle events",
        "memory": "Graphify, MemPalace, and sanitized rule synthesis",
        "context7_surface": "Optional Context7 MCP surface",
        "redis_surface": "Optional Redis cache/pub-sub/lock surface",
        "helm_surface": "Optional Helm/HPA deployment surface",
        "independent_acceptance": "Generated product and canonical fixture acceptance",
        "artifacts": "Plan/diff/test/review/risk/PR artifact evidence",
    }
    passed = sum(item.get("status") == "PASS" for item in conformance.values())
    lines = [
        "# ForgeOS Reference ForgeLedger PRD Benchmark",
        "",
        f"- Status: **{metrics.get('status')}**",
        f"- README claims checked: **{passed}/{len(conformance)} PASS**",
        f"- Workspace: {metrics.get('workspace')}",
        f"- PRD: {metrics.get('prd_file')}",
        "",
        "## README claim versus observed evidence",
        "",
        "| Claim | Evidence | Status |",
        "| --- | --- | --- |",
    ]
    for name, item in conformance.items():
        lines.append(
            f"| {labels.get(name, name)} | {item.get('evidence', '')} | **{item.get('status')}** |"
        )
    goal = (control_plane or {}).get("goal", {})
    todos = (control_plane or {}).get("todos", [])
    lines.extend(
        [
            "",
            "## Control-plane evidence",
            "",
            f"- Goal status: **{goal.get('status')}**",
            f"- Todos: **{[(todo.get('todo_id'), todo.get('status')) for todo in todos]}**",
            f"- Receipts: **{len((control_plane or {}).get('receipts', []))}**",
            "",
            "This report is generated after the real ForgeOS run from SQLite, the",
            "durable control-plane snapshot, independent product tests, canonical",
            "fixtures, and bounded platform probes. It does not edit generated",
            "product code or convert optional integration surfaces into live proof.",
        ]
    )
    (base.EVIDENCE / base.REPORT_FILENAME).write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _publish_latest_evidence() -> None:
    """Publish stable README targets only after an accepted run.

    Timestamped evidence remains the immutable source of truth. These stable
    copies make the README useful between reruns without allowing a blocked or
    partial run to overwrite the last accepted snapshot.
    """
    LATEST_EVIDENCE.mkdir(parents=True, exist_ok=True)
    for filename in (
        base.REPORT_FILENAME,
        base.METRICS_FILENAME,
        "acceptance_report.md",
        "control_plane.json",
        "events.jsonl",
        "manifest.json",
    ):
        source = base.EVIDENCE / filename
        if source.is_file():
            shutil.copyfile(source, LATEST_EVIDENCE / filename)


async def main() -> int:
    base.cloud._explicit_free_routes = _select_reference_routes
    code = await base.main()
    base.EVIDENCE.mkdir(parents=True, exist_ok=True)
    metrics_path = base.EVIDENCE / base.METRICS_FILENAME
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    final = _final_acceptance()
    probes = await _platform_probes()
    database = base.WORKSPACE / ".localforge" / "localforge.db"
    artifacts = _artifact_types(database) if database.is_file() else {}
    control_plane, event_text = _control_plane_snapshot()
    conformance = _conformance(metrics, final, probes, artifacts)
    core_names = {
        "omniroute_gateway",
        "prd_pipeline",
        "control_plane",
        "independent_acceptance",
        "artifacts",
        "typed_agent_harness",
        "durable_harness_state",
        "bounded_subagents",
        "skills",
        "safety_hooks",
        "observability",
        "memory",
    }
    core_pass = all(conformance[name]["status"] == "PASS" for name in core_names)
    if not core_pass:
        if metrics.get("status") == "ACCEPTED":
            metrics["status"] = "PARTIAL"
        metrics.setdefault("blockers", []).append(
            "One or more README core conformance claims failed"
        )
    metrics["final_validation"] = final
    metrics["platform_conformance"] = conformance
    metrics["artifact_types"] = artifacts
    metrics["control_plane_export"] = {
        "present": control_plane is not None,
        "events_lines": len((event_text or "").splitlines()),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    _write_report(metrics, conformance, control_plane)
    if control_plane is not None:
        (base.EVIDENCE / "control_plane.json").write_text(
            json.dumps(control_plane, indent=2) + "\n",
            encoding="utf-8",
        )
    if event_text is not None:
        (base.EVIDENCE / "events.jsonl").write_text(event_text, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "benchmark": base.BENCHMARK_LABEL,
        "status": metrics.get("status"),
        "workspace": str(base.WORKSPACE.relative_to(ROOT)).replace("\\", "/"),
        "evidence": str(base.EVIDENCE.relative_to(ROOT)).replace("\\", "/"),
        "metrics": base.METRICS_FILENAME,
        "report": base.REPORT_FILENAME,
        "control_plane": "control_plane.json" if control_plane else None,
        "events": "events.jsonl" if event_text is not None else None,
        "exit_code": 0 if metrics.get("status") == "ACCEPTED" else max(code, 2),
    }
    (base.EVIDENCE / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (base.EVIDENCE / "acceptance_report.md").write_text(
        (base.EVIDENCE / base.REPORT_FILENAME).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    if metrics.get("status") == "ACCEPTED":
        _publish_latest_evidence()
    print(json.dumps(metrics, indent=2))
    return 0 if metrics.get("status") == "ACCEPTED" else max(code, 2)


async def _platform_probes() -> dict[str, dict[str, Any]]:
    """Exercise ForgeOS contracts without modifying the generated product."""

    results: dict[str, dict[str, Any]] = {}

    def ok(name: str, evidence: str) -> None:
        results[name] = {"status": "PASS", "evidence": evidence}

    def bad(name: str, error: Exception) -> None:
        results[name] = {"status": "FAIL", "evidence": str(error)[:500]}

    with tempfile.TemporaryDirectory(prefix="forgeos-reference-platform-") as directory:
        root = Path(directory)
        try:
            harness = AgentHarness()
            contract = harness.contract_for(
                role="Developer",
                method="bounded_change",
                strategy="auto",
                max_retries=1,
                context_budget=1000,
            )
            rendered, included = compact_context(
                [
                    ContextBlock(name="required", content="contract", required=True),
                    ContextBlock(name="optional", content="discardable", priority=1),
                ],
                budget=1000,
            )
            assert contract.strategy.value == "code_act"
            assert rendered and "required" in included
            ok("typed_agent_harness", "code_act strategy and required context retained")
        except Exception as exc:
            bad("typed_agent_harness", exc)

        try:
            state = HarnessState(root)
            state.upsert(
                HarnessEntry(
                    id="system",
                    kind="prompt",
                    scope="project",
                    content="immutable base",
                    supplemental=False,
                    is_system_prompt=True,
                    is_base=True,
                )
            )
            memory = state.upsert(
                HarnessEntry(
                    id="memory-1",
                    kind="memory",
                    scope="project",
                    content={"decision": "JSON persistence"},
                )
            )
            event = state.refine(
                memory.id,
                {"source": "reference-test"},
                {"metadata": {"validated": True}},
            )
            restored = HarnessState(root).get(memory.id)
            assert restored is not None and restored.metadata["validated"] is True
            assert state.list_snapshots() and event.entry_id == memory.id
            try:
                state.refine("system", {"attempt": "overwrite"}, {"content": "unsafe"})
            except ValueError:
                pass
            else:
                raise AssertionError("system prompt refinement was not rejected")
            ok("durable_harness_state", "snapshots, refinement, persistence, and prompt protection")
        except Exception as exc:
            bad("durable_harness_state", exc)

        try:
            registry = SubagentRegistry(HarnessStateSubagentStore(HarnessState(root)))
            parent = registry.register(
                SubagentSpec(
                    id="reference-parent",
                    task="inspect",
                    role="Reviewer",
                    max_depth=1,
                    max_turns=2,
                    max_tokens=128,
                )
            )
            child = registry.register_child(
                parent.id,
                SubagentSpec(
                    id="reference-child",
                    task="verify",
                    role="QA",
                    max_depth=0,
                    max_turns=1,
                    max_tokens=64,
                ),
            )
            registry.start(child.id)
            registry.complete(child.id, result={"passed": True}, evidence=["fixture"])
            try:
                registry.resume(child.id)
            except Exception:
                pass
            else:
                raise AssertionError("terminal subagent resumed")
            ok("bounded_subagents", "durable parent-child lifecycle and terminal protection")
        except Exception as exc:
            bad("bounded_subagents", exc)

        try:
            registry = SkillRegistry(str(root))
            names = {skill.name for skill in registry.load_all()}
            assert {"grill-with-docs", "to-tickets", "tdd"}.issubset(names)
            custom = registry.write_local(
                SkillDefinition(
                    name="reference-custom",
                    purpose="bounded reference skill",
                    strategy="predict",
                    runtime="instruction",
                )
            )
            result = await SkillExecutor(registry).execute(
                custom,
                SkillExecutionContext(granted_permissions=frozenset()),
            )
            assert result.status == "DECLARATIVE_ONLY"
            ok("skills", "three workflow skills and a persisted custom manifest")
        except Exception as exc:
            bad("skills", exc)

        try:
            executed = {"value": False}

            async def before(call: ToolCall) -> ToolPolicyDecision:
                return ToolPolicyDecision(allowed=False, reason="reference policy gate")

            async def tool_executor() -> None:
                executed["value"] = True

            protected = AgentHarness(tool_policy=FunctionalToolPolicy(before=before))
            try:
                await protected.execute_tool(
                    ToolCall(name="run_command", call_id="reference-safety"),
                    tool_executor,
                )
            except ToolPolicyDenied:
                pass
            else:
                raise AssertionError("blocked tool executed")
            assert executed["value"] is False
            ok("safety_hooks", "pre-execution hook denied the tool before executor")
        except Exception as exc:
            bad("safety_hooks", exc)

        try:
            tracer = OpenTelemetryTracer()
            parent = tracer.start_span("Reviewer", "review")
            tracer.emit_event("agent_start", span_id=parent.span_id)
            child = tracer.start_span("tool", "read", parent_span_id=parent.span_id)
            tracer.emit_event("tool_execution_start", span_id=child.span_id)
            tracer.end_span(child.span_id)
            tracer.end_span(parent.span_id)
            assert child.root_span_id == parent.span_id and len(tracer.get_events()) == 2
            ok("observability", "nested spans and ordered lifecycle events")
        except Exception as exc:
            bad("observability", exc)

        previous_cache = os.environ.get("FORGEOS_SEMANTIC_CACHE_ENABLED")
        try:
            os.environ["FORGEOS_SEMANTIC_CACHE_ENABLED"] = "false"
            (root / "sample.py").write_text("import json\\njson.loads('{}')\\n", encoding="utf-8")
            graph = GraphifyEngine(root).build_codebase_graph()
            palace = MemPalaceService(root / "memories")
            palace.save_loci_memory("project", "decisions", {"decision": "keep JSON"})
            assert palace.recall_project_memories("project", "decisions")
            (root / "AGENTS.md").write_text("# Instructions\\n", encoding="utf-8")
            assert RuleSynthesizer(root).synthesize_and_inject_rule(
                "reference", "Keep acceptance tests behavioral."
            )
            assert graph["nodes_count"] >= 1
            ok("memory", "Graphify, MemPalace recall, and sanitized rule synthesis")
        except Exception as exc:
            bad("memory", exc)
        finally:
            if previous_cache is None:
                os.environ.pop("FORGEOS_SEMANTIC_CACHE_ENABLED", None)
            else:
                os.environ["FORGEOS_SEMANTIC_CACHE_ENABLED"] = previous_cache

        try:
            assert Context7MCPConnector._extract_library_id(
                {"result": {"content": [{"type": "text", "text": "Use /reactjs/react.dev"}]}}
            ) == "/reactjs/react.dev"
            ok("context7_surface", "MCP parser and endpoint surface present; live service not required")
        except Exception as exc:
            bad("context7_surface", exc)

        try:
            manager = RedisManager(redis_url="redis://127.0.0.1:63999/0")
            assert all(
                hasattr(manager, method)
                for method in ("get", "set", "publish", "acquire_lock")
            )
            ok("redis_surface", "optional cache, pub-sub, and lock interface present; server not required")
        except Exception as exc:
            bad("redis_surface", exc)

    helm_files = [
        ROOT / "deploy" / "helm" / "forgeos-cloud" / "Chart.yaml",
        ROOT / "deploy" / "helm" / "forgeos-cloud" / "templates" / "hpa-sandbox.yaml",
    ]
    if all(path.is_file() for path in helm_files):
        ok("helm_surface", "optional chart and HPA template present")
    else:
        bad("helm_surface", FileNotFoundError("Helm chart surface is incomplete"))
    return results


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
