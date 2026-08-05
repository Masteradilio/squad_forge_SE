"""Exercise V8 interruption, recovery, idempotency, and blocker handoff semantics."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from localforge.control_plane import (  # noqa: E402
    ControlPlaneKernel,
    ControlPlaneStore,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
    TurnRoute,
)


WORKSPACE = ROOT / "benchmarks" / "workspaces" / "v8-recovery-fixture"
EVIDENCE = ROOT / "docs" / "e2e" / "v8" / "recovery_fixture"
STATE_PATH = WORKSPACE / "control_plane.json"


def _remove_runtime_state() -> None:
    for path in (
        STATE_PATH,
        STATE_PATH.with_suffix(".events.jsonl"),
        STATE_PATH.with_suffix(".json.lock"),
    ):
        if path.exists():
            path.unlink()


def _expire_claimed_turn(store: ControlPlaneStore) -> None:
    def mutate(state):
        assert state is not None
        state.todos[0].lease_expires_at = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
        return state

    store.update(mutate, operation_id="fixture:expire-lease")


def main() -> int:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    _remove_runtime_state()
    store = ControlPlaneStore(STATE_PATH)
    kernel = ControlPlaneKernel(store)
    kernel.start(
        goal_id="v8:recovery-fixture",
        vision="prove restartable bounded work",
        non_negotiables=["no duplicate receipt", "preserve blocker evidence"],
        tasks=[
            TaskSnapshot(todo_id="A", title="interrupted lane", status="READY"),
            TaskSnapshot(todo_id="B", title="repair lane", status="READY"),
        ],
        max_attempts_per_todo=3,
        max_turns=10,
    )

    first = kernel.next_turn("worker-before-restart")
    assert first.route == TurnRoute.READY and first.todo_id == "A"
    _expire_claimed_turn(store)

    restarted = ControlPlaneKernel(ControlPlaneStore(STATE_PATH))
    recovered = restarted.next_turn("worker-after-restart")
    assert recovered.route == TurnRoute.READY and recovered.todo_id == "A"
    restarted.record_result(
        TurnResult(
            todo_id="A",
            turn_id=recovered.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_PROGRESS,
            summary="recovered after lease expiry",
            validated_by="worker-after-restart",
            idempotency_key="recovery-a",
        )
    )

    failed = restarted.next_turn("worker-after-restart")
    assert failed.route == TurnRoute.READY and failed.todo_id == "B"
    restarted.record_result(
        TurnResult(
            todo_id="B",
            turn_id=failed.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATION_FAILED,
            summary="injected validation blocker",
            evidence={"check": "fixture", "exit_code": 1},
            validated_by="checker",
            idempotency_key="recovery-b-failure",
        )
    )
    repair = restarted.next_turn("scrum-master")
    assert repair.route == TurnRoute.REPAIR and repair.todo_id == "B"
    restarted.record_repair_handoff(
        todo_id="B",
        diagnosis="injected validation blocker",
        evidence={"authority": "scrum_master", "next": "chief_engineer"},
        handoff_id="recovery-b-handoff",
    )
    restarted.reopen_after_repair(
        todo_id="B",
        summary="chief repair passed fixture check",
        evidence={"check": "fixture", "exit_code": 0},
        handoff_id="recovery-b-handoff",
    )
    repaired = restarted.next_turn("chief-engineer")
    assert repaired.route == TurnRoute.READY and repaired.todo_id == "B"
    final_result = TurnResult(
        todo_id="B",
        turn_id=repaired.turn_id or "missing",
        result_kind=TurnResultKind.VALIDATED_COMPLETION,
        summary="repaired and validated",
        evidence={"check": "fixture", "exit_code": 0},
        validated_by="chief-engineer",
        idempotency_key="recovery-b-success",
    )
    completed = restarted.record_result(final_result)
    duplicate = restarted.record_result(final_result)
    assert completed.goal.status.value == "COMPLETED"
    assert len(duplicate.receipts) == 3
    assert restarted.store.verify_replay()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    final_state = ControlPlaneStore(STATE_PATH).read()
    assert final_state is not None
    (EVIDENCE / "control_plane.json").write_text(
        final_state.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (EVIDENCE / "events.jsonl").write_text(
        STATE_PATH.with_suffix(".events.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    metrics = {
        "schema_version": 1,
        "benchmark": "ForgeOS V8 interruption and blocker recovery fixture",
        "status": "ACCEPTED",
        "interruption_recovered": True,
        "injected_blocker_repaired": True,
        "duplicate_writeback_receipts": 0,
        "receipts": len(duplicate.receipts),
        "journal_verified": restarted.store.verify_replay(),
        "final_goal_status": duplicate.goal.status.value,
        "final_todo_statuses": [item.status.value for item in duplicate.todos],
    }
    (EVIDENCE / "metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark": metrics["benchmark"],
                "status": metrics["status"],
                "control_plane": "control_plane.json",
                "events": "events.jsonl",
                "metrics": "metrics.json",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE / "acceptance_report.md").write_text(
        "# V8 Recovery Fixture\n\n"
        "- Status: **ACCEPTED**\n"
        "- Lease interruption recovered after process restart: **yes**\n"
        "- Injected validation blocker repaired through handoff: **yes**\n"
        "- Duplicate writeback receipts: **0**\n"
        "- Journal replay verified: **yes**\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
