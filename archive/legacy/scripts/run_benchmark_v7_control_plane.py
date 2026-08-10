"""Run the fast V7 control-plane benchmark without model or network calls."""

from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from localforge.control_plane import (
    ControlPlaneKernel,
    ControlPlaneStore,
    GateState,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
    TurnRoute,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "e2e" / "v7"


def _kernel(path: Path) -> ControlPlaneKernel:
    return ControlPlaneKernel(ControlPlaneStore(path))


def _receipt(
    *,
    todo_id: str,
    turn_id: str,
    result_kind: TurnResultKind,
    summary: str,
    key: str,
    changed_files: list[str] | None = None,
    checks: list[str] | None = None,
) -> TurnResult:
    return TurnResult(
        todo_id=todo_id,
        turn_id=turn_id,
        result_kind=result_kind,
        summary=summary,
        evidence={"source": "v7_control_plane_benchmark", "validated": True},
        validated_by="forgeos.benchmark.verifier",
        idempotency_key=key,
        changed_files=changed_files or [],
        checks=checks or [],
        source_revision="benchmark-source",
    )


def run() -> dict[str, Any]:
    started = time.monotonic()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forgeos-v7-") as temp_dir:
        state_path = Path(temp_dir) / "control_plane.json"
        kernel = _kernel(state_path)
        kernel.start(
            goal_id="v7:mini-control-plane",
            vision="Complete the Mini Control Plane PRD with reviewable evidence.",
            non_negotiables=[
                "No progress without a validated receipt.",
                "No unbounded retries.",
                "No merge or deployment authority.",
            ],
            scope=["docs/e2e/v7/PRD_MINI_CONTROL_PLANE.md"],
            authority={
                "scrum_master": "diagnose_and_delegate",
                "chief_engineer": "repair_under_contract",
                "human": "approve_merge",
            },
            gates=[GateState(gate_id="review-evidence", name="Review evidence")],
            tasks=[
                TaskSnapshot(todo_id="MINI-001", title="Create skeleton", status="READY"),
                TaskSnapshot(
                    todo_id="MINI-002",
                    title="Add checks",
                    status="READY",
                    dependencies=["MINI-001"],
                ),
                TaskSnapshot(
                    todo_id="MINI-003",
                    title="Assemble evidence",
                    status="READY",
                    dependencies=["MINI-002"],
                ),
            ],
            max_turns=8,
            max_attempts_per_todo=3,
            max_cost_usd=0.05,
            max_wall_seconds=30,
        )

        first = kernel.next_turn("scheduler")
        assert first.route == TurnRoute.READY and first.todo_id == "MINI-001"
        kernel.record_result(
            _receipt(
                todo_id="MINI-001",
                turn_id=first.turn_id or "",
                result_kind=TurnResultKind.VALIDATED_PROGRESS,
                summary="Skeleton validated.",
                key="mini-001-pass-1",
                changed_files=["app/mini_board.py"],
                checks=["python -m compileall app/mini_board.py"],
            )
        )

        second = kernel.next_turn("scheduler")
        assert second.route == TurnRoute.READY and second.todo_id == "MINI-002"
        kernel.record_result(
            _receipt(
                todo_id="MINI-002",
                turn_id=second.turn_id or "",
                result_kind=TurnResultKind.VALIDATION_FAILED,
                summary="The first deterministic check failed once.",
                key="mini-002-failure-1",
                checks=["pytest -q"],
            )
        )
        repair = kernel.next_turn("scheduler")
        assert repair.route == TurnRoute.REPAIR and repair.todo_id == "MINI-002"
        kernel.record_repair_handoff(
            todo_id="MINI-002",
            diagnosis="The deterministic check failed once.",
            evidence={"failed_check": "pytest -q", "owner": "scrum_master"},
            handoff_id="mini-002-repair-1",
        )
        kernel.reopen_after_repair(
            todo_id="MINI-002",
            summary="Chief repair completed and check is ready to rerun.",
            evidence={"repair_owner": "chief_engineer", "rerun_required": True},
            handoff_id="mini-002-repair-1",
        )

        # Recreate the kernel to prove the next frontier is externalized.
        restarted = _kernel(state_path)
        repaired_turn = restarted.next_turn("scheduler")
        assert repaired_turn.route == TurnRoute.READY
        assert repaired_turn.todo_id == "MINI-002"
        restarted.record_result(
            _receipt(
                todo_id="MINI-002",
                turn_id=repaired_turn.turn_id or "",
                result_kind=TurnResultKind.VALIDATED_PROGRESS,
                summary="Checks pass after bounded repair.",
                key="mini-002-pass-2",
                changed_files=["tests/test_mini_board.py"],
                checks=["pytest -q"],
            )
        )

        final_turn = restarted.next_turn("scheduler")
        assert final_turn.route == TurnRoute.READY and final_turn.todo_id == "MINI-003"
        restarted.record_result(
            _receipt(
                todo_id="MINI-003",
                turn_id=final_turn.turn_id or "",
                result_kind=TurnResultKind.VALIDATED_COMPLETION,
                summary="Review evidence assembled.",
                key="mini-003-pass-1",
                changed_files=["docs/mini-pr.md"],
                checks=["receipt-schema", "dependency-frontier"],
            )
        )
        final_state = restarted.status()
        assert final_state is not None
        assert final_state.goal.status.value == "COMPLETED"
        assert all(todo.status.value == "PASSED" for todo in final_state.todos)
        assert len(final_state.receipts) == 4
        assert any(event.get("event") == "repair_handoff" for event in final_state.events)
        assert any(event.get("event") == "repair_writeback" for event in final_state.events)

        projection = final_state.model_dump(mode="json")
        projection_path = EVIDENCE_DIR / "control_plane.json"
        projection_path.write_text(json.dumps(projection, indent=2) + "\n", encoding="utf-8")

        elapsed = round(time.monotonic() - started, 3)
        metrics = {
            "benchmark_name": "ForgeOS V7 Mini Control Plane",
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "ACCEPTED",
            "execution_mode": "deterministic_control_plane_fixture",
            "model_calls": 0,
            "human_interventions": 0,
            "task_count": len(final_state.todos),
            "passed_tasks": len(final_state.todos),
            "receipts": len(final_state.receipts),
            "repair_handoffs": sum(
                event.get("event") == "repair_handoff" for event in final_state.events
            ),
            "turns_started": final_state.quota.turns_started,
            "turns_committed": final_state.quota.turns_committed,
            "elapsed_seconds": elapsed,
            "state_revision": final_state.revision,
            "limitations": [
                "This benchmark validates the durable control plane, not model coding quality.",
                "A real PRD benchmark must separately exercise the scheduler and provider gateway.",
            ],
        }
        metrics_path = EVIDENCE_DIR / "mini_control_plane_metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        report_path = EVIDENCE_DIR / "mini_control_plane_acceptance.md"
        report_path.write_text(
            "# V7 Mini Control Plane Acceptance\n\n"
            "- Status: **ACCEPTED**\n"
            f"- Tasks passed: **{len(final_state.todos)}/{len(final_state.todos)}**\n"
            f"- Receipts: **{len(final_state.receipts)}**\n"
            f"- Repair handoffs: **{metrics['repair_handoffs']}**\n"
            f"- Bounded turns: **{final_state.quota.turns_started} started / "
            f"{final_state.quota.turns_committed} committed**\n"
            f"- Human interventions: **{metrics['human_interventions']}**\n"
            f"- Elapsed wall time: **{elapsed}s**\n\n"
            "This is a control-plane acceptance fixture. It proves durable resume, "
            "typed blocker recovery, and final writeback; it does not claim that a "
            "model generated a production product.\n",
            encoding="utf-8",
        )
        return metrics


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
