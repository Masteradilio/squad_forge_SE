"""Run the pause/restart/lease recovery proof required by PA-010."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from localforge.control_plane import (
    ControlPlaneKernel,
    ControlPlaneStore,
    PersistentRunnerPolicy,
    PersistentWorkerRunner,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
)


def _start(path: Path) -> ControlPlaneKernel:
    kernel = ControlPlaneKernel(ControlPlaneStore(path))
    kernel.start(
        goal_id="compliance:recovery",
        vision="recover a bounded executor after restart",
        non_negotiables=["do not duplicate receipt"],
        tasks=[TaskSnapshot(todo_id="A", title="recoverable task", status="READY")],
        source_revision="recovery-source-1",
        acceptance_target="recovered_once",
    )
    return kernel


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forgeos-recovery-") as temp:
        state_path = Path(temp) / "control-plane.json"
        first = _start(state_path)
        claimed = first.next_turn("executor-a", lease_seconds=60)

        def expire(state):
            state.todos[0].lease_expires_at = "2000-01-01T00:00:00+00:00"
            return state

        first.store.update(expire, operation_id="compliance:expire-lease")
        restarted = ControlPlaneKernel(ControlPlaneStore(state_path))
        runner = PersistentWorkerRunner(
            restarted,
            lambda decision: TurnResult(
                todo_id=decision.todo_id or "missing",
                turn_id=decision.turn_id or "missing",
                result_kind=TurnResultKind.VALIDATED_COMPLETION,
                summary="recovered after executor restart",
                validated_by="replacement-executor",
                evidence={"restart": True, "lease_recovered": True},
                idempotency_key="compliance:recovery:receipt:A",
            ),
            sleeper=lambda _: None,
        )
        outcome = runner.run(PersistentRunnerPolicy(owner="executor-b", lease_seconds=60, max_ticks=2))
        state = restarted.status()
        events = state.events if state is not None else []
        recovered = any(
            event.get("event") == "lease_expired_recovered" and event.get("turn_id") == claimed.turn_id
            for event in events
        )
        report = {
            "schema": "forgeos.recovery_compliance.v1",
            "status": "PASS" if outcome.status == "COMPLETED" and recovered else "FAIL",
            "initial_turn_id": claimed.turn_id,
            "outcome": asdict(outcome),
            "lease_recovered": recovered,
            "event_count": len(events),
            "goal_status": state.goal.status.value if state is not None else None,
            "receipt_ids": [receipt.receipt_id for receipt in (state.receipts if state is not None else [])],
        }
    (output / "recovery_compliance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
