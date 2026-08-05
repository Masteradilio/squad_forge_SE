"""Small bounded worker bridge for external heartbeats.

The bridge never executes shell or model actions itself. A trusted ForgeOS
executor supplies one callback for the already-claimed turn, while the
control-plane kernel owns leases, receipts, quota, and the next decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from localforge.control_plane.contracts import (
    ControlPlaneState,
    TurnDecision,
    TurnResult,
    TurnResultKind,
    TurnRoute,
)
from localforge.control_plane.kernel import ControlPlaneKernel


@dataclass(frozen=True)
class WorkerTick:
    decision: TurnDecision
    state: ControlPlaneState | None = None
    error: str | None = None


class BoundedWorkerBridge:
    """Expose claim/writeback as one restartable, bounded worker tick."""

    def __init__(self, kernel: ControlPlaneKernel) -> None:
        self.kernel = kernel

    def should_run(self) -> dict[str, object]:
        return self.kernel.should_run()

    def recover_expired_leases(self) -> ControlPlaneState | None:
        return self.kernel.recover_expired_leases()

    def claim(
        self,
        owner: str,
        *,
        lease_seconds: int = 900,
        expected_revision: int | None = None,
    ) -> TurnDecision:
        return self.kernel.next_turn(
            owner,
            lease_seconds=lease_seconds,
            expected_revision=expected_revision,
        )

    def writeback(self, result: TurnResult) -> ControlPlaneState:
        return self.kernel.record_result(result)

    def renew_lease(
        self,
        *,
        todo_id: str,
        turn_id: str,
        lease_token: str,
        lease_seconds: int = 900,
        owner: str | None = None,
        renewal_id: str | None = None,
    ) -> ControlPlaneState:
        return self.kernel.renew_lease(
            todo_id=todo_id,
            turn_id=turn_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            owner=owner,
            renewal_id=renewal_id,
        )

    def execute_once(
        self,
        owner: str,
        executor: Callable[[TurnDecision], TurnResult],
        *,
        lease_seconds: int = 900,
        expected_revision: int | None = None,
    ) -> WorkerTick:
        """Run one callback and convert host exceptions into typed failure."""

        decision = self.claim(
            owner,
            lease_seconds=lease_seconds,
            expected_revision=expected_revision,
        )
        if decision.route != TurnRoute.READY:
            return WorkerTick(decision=decision, state=self.kernel.status())
        if not decision.todo_id or not decision.turn_id:
            raise RuntimeError("READY decision must contain todo_id and turn_id")
        try:
            result = executor(decision)
        except Exception as exc:  # pragma: no cover - exercised by integration users
            result = TurnResult(
                todo_id=decision.todo_id,
                turn_id=decision.turn_id,
                result_kind=TurnResultKind.HOST_FAILURE,
                summary=f"worker callback failed: {exc!r}",
                evidence={"worker": owner, "exception": repr(exc)},
                validated_by="forgeos.worker_bridge",
                idempotency_key=f"host-failure:{decision.turn_id}",
            )
        return WorkerTick(decision=decision, state=self.writeback(result))
