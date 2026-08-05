"""Persistent, bounded host runner for the ForgeOS interaction contract."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal

from localforge.control_plane.contracts import (
    ControlPlaneState,
    TurnDecision,
    TurnResult,
    TurnResultKind,
    TurnRoute,
)
from localforge.control_plane.kernel import ControlPlaneKernel
from localforge.control_plane.worker import BoundedWorkerBridge


RunnerStatus = Literal["COMPLETED", "STOPPED", "BLOCKED", "WAITING", "EXHAUSTED"]


@dataclass(frozen=True)
class PersistentRunnerPolicy:
    """Operational bounds for a host process; never model policy."""

    owner: str = "persistent-worker"
    lease_seconds: int = 900
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    max_ticks: int | None = None
    stop_file: str | Path | None = None


@dataclass(frozen=True)
class PersistentRunnerOutcome:
    status: RunnerStatus
    ticks: int
    progress_events: int
    signal_wakeups: int
    last_route: str | None = None


class PersistentWorkerRunner:
    """Keep a durable goal moving through bounded, restartable host ticks.

    The runner owns waiting, backoff, lease recovery, and dispatch. It does
    not choose task policy or execute models itself; the supplied callbacks do
    that under the kernel's typed contracts.
    """

    def __init__(
        self,
        kernel: ControlPlaneKernel,
        execute: Callable[[TurnDecision], TurnResult],
        *,
        on_repair: Callable[[TurnDecision], None] | None = None,
        on_signal: Callable[[dict[str, object]], None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.kernel = kernel
        self.bridge = BoundedWorkerBridge(kernel)
        self.execute = execute
        self.on_repair = on_repair
        self.on_signal = on_signal
        self.sleeper = sleeper

    def run(self, policy: PersistentRunnerPolicy | None = None) -> PersistentRunnerOutcome:
        policy = policy or PersistentRunnerPolicy()
        if policy.lease_seconds < 30:
            raise ValueError("lease_seconds must be at least 30 seconds")
        if policy.base_backoff_seconds <= 0 or policy.max_backoff_seconds <= 0:
            raise ValueError("backoff values must be positive")
        if policy.base_backoff_seconds > policy.max_backoff_seconds:
            raise ValueError("base backoff cannot exceed max backoff")

        ticks = 0
        progress_events = 0
        signal_wakeups = 0
        backoff = policy.base_backoff_seconds
        last_route: str | None = None

        while True:
            if self._stop_requested(policy):
                return PersistentRunnerOutcome(
                    "STOPPED", ticks, progress_events, signal_wakeups, last_route
                )
            if policy.max_ticks is not None and ticks >= policy.max_ticks:
                return PersistentRunnerOutcome(
                    "EXHAUSTED", ticks, progress_events, signal_wakeups, last_route
                )
            ticks += 1

            # Restart recovery is deterministic and does not spend model
            # budget. It releases only leases whose expiry is already known.
            self.bridge.recover_expired_leases()
            packet = self.bridge.should_run()
            contract = packet.get("interaction_contract", {})
            if not isinstance(contract, dict):
                raise RuntimeError("Invalid interaction contract projection")
            next_action = packet.get("next_action")
            route = (
                str(next_action.get("route"))
                if isinstance(next_action, dict)
                else None
            )
            last_route = route

            if contract.get("primary_action") == "inspect_external_signal":
                signal_wakeups += 1
                signal = self._first_unacknowledged_signal(packet)
                before = self.kernel.status()
                if signal is not None and self.on_signal is not None:
                    self.on_signal(signal)
                after = self.kernel.status()
                if self._state_progressed(before, after):
                    progress_events += 1
                    backoff = policy.base_backoff_seconds
                else:
                    self.sleeper(backoff)
                    backoff = min(policy.max_backoff_seconds, backoff * 2)
                continue

            should_run = bool(contract.get("should_run"))
            if not should_run:
                if route == TurnRoute.COMPLETE.value:
                    return PersistentRunnerOutcome(
                        "COMPLETED", ticks, progress_events, signal_wakeups, last_route
                    )
                if route in {TurnRoute.ASK.value, TurnRoute.BLOCKED.value}:
                    return PersistentRunnerOutcome(
                        "BLOCKED", ticks, progress_events, signal_wakeups, last_route
                    )
                self.sleeper(self._wait_seconds(contract, backoff))
                backoff = min(policy.max_backoff_seconds, backoff * 2)
                continue

            decision = self.bridge.claim(
                policy.owner,
                lease_seconds=policy.lease_seconds,
            )
            last_route = decision.route.value
            if decision.route == TurnRoute.READY:
                try:
                    result = self.execute(decision)
                except Exception as exc:
                    result = TurnResult(
                        todo_id=decision.todo_id or "missing",
                        turn_id=decision.turn_id or "missing",
                        result_kind=TurnResultKind.HOST_FAILURE,
                        summary=f"persistent worker callback failed: {exc!r}",
                        evidence={
                            "runner": "forgeos.persistent_worker",
                            "owner": policy.owner,
                            "exception": repr(exc),
                        },
                        validated_by="forgeos.persistent_worker",
                        idempotency_key=f"persistent-host-failure:{decision.turn_id}",
                    )
                self.bridge.writeback(result)
                if result.result_kind in {
                    TurnResultKind.VALIDATED_PROGRESS,
                    TurnResultKind.VALIDATED_COMPLETION,
                }:
                    progress_events += 1
                    if result.result_kind == TurnResultKind.VALIDATED_COMPLETION:
                        return PersistentRunnerOutcome(
                            "COMPLETED",
                            ticks,
                            progress_events,
                            signal_wakeups,
                            last_route,
                        )
                    backoff = policy.base_backoff_seconds
                else:
                    self.sleeper(backoff)
                    backoff = min(policy.max_backoff_seconds, backoff * 2)
                continue

            if decision.route in {TurnRoute.REPAIR, TurnRoute.REPLAN} and self.on_repair:
                before = self.kernel.status()
                self.on_repair(decision)
                after = self.kernel.status()
                if self._state_progressed(before, after):
                    progress_events += 1
                    backoff = policy.base_backoff_seconds
                    continue

            self.sleeper(backoff)
            backoff = min(policy.max_backoff_seconds, backoff * 2)

    @staticmethod
    def _stop_requested(policy: PersistentRunnerPolicy) -> bool:
        return policy.stop_file is not None and Path(policy.stop_file).exists()

    @staticmethod
    def _first_unacknowledged_signal(
        packet: dict[str, object],
    ) -> dict[str, object] | None:
        signals = packet.get("signals", [])
        if not isinstance(signals, list):
            return None
        for signal in signals:
            if isinstance(signal, dict) and signal.get("acknowledged_at") is None:
                return signal
        return None

    @staticmethod
    def _state_progressed(
        before: ControlPlaneState | None, after: ControlPlaneState | None
    ) -> bool:
        return bool(
            before is not None and after is not None and after.revision > before.revision
        )

    @staticmethod
    def _wait_seconds(contract: dict[str, object], fallback: float) -> float:
        wait_until = contract.get("wait_until")
        if isinstance(wait_until, str) and wait_until:
            try:
                remaining = (
                    datetime.fromisoformat(wait_until) - datetime.now(UTC)
                ).total_seconds()
                return max(0.1, min(fallback, remaining))
            except ValueError:
                pass
        return fallback
