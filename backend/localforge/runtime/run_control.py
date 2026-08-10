"""Deterministic continuation-policy projections for bounded runs.

This module does not schedule work, sleep, retry providers, or mutate control
plane state.  Callers provide current counters and elapsed time, and receive a
pure policy decision plus an optional filesystem pause signal.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunContinuationPolicy(BaseModel):
    """Limits and externally supplied quality-gate names for one bounded run."""

    model_config = ConfigDict(extra="forbid")

    max_turns: int = Field(default=1, gt=0)
    max_wall_seconds: float | None = Field(default=None, gt=0)
    max_retries: int = Field(default=0, ge=0)
    pause_file: Path | None = None
    quality_gate_names: list[str] = Field(default_factory=list)

    def check_pause(self) -> bool:
        """Return whether the configured pause marker currently exists."""

        return self.pause_file is not None and self.pause_file.exists()

    def should_continue(
        self,
        turns: int | None = None,
        elapsed_seconds: float | None = None,
        retries: int | None = None,
        *,
        turn_count: int | None = None,
        wall_seconds: float | None = None,
        quality_gates_passed: bool | None = None,
        completed_quality_gates: Iterable[str] | None = None,
        quality_gates: Mapping[str, Any] | None = None,
    ) -> bool:
        """Evaluate the policy from explicit, deterministic run observations.

        ``turns`` and ``elapsed_seconds`` represent work already consumed.  A
        retry count is checked when supplied; omitting it lets callers use this
        helper for ordinary turn admission without conflating retries with
        turns.  When gate results are supplied, every configured gate must be
        passed.  Gate names alone do not execute or discover gates.
        """

        turns = self._resolve_alias(turns, turn_count, "turns", "turn_count")
        elapsed_seconds = self._resolve_alias(
            elapsed_seconds,
            wall_seconds,
            "elapsed_seconds",
            "wall_seconds",
        )
        if turns is None:
            raise TypeError("should_continue requires turns or turn_count.")
        if elapsed_seconds is None:
            elapsed_seconds = 0.0
        self._validate_counter(turns, "turns")
        self._validate_counter(elapsed_seconds, "elapsed_seconds")
        if retries is not None:
            self._validate_counter(retries, "retries")

        if self.check_pause():
            return False
        if turns >= self.max_turns:
            return False
        if self.max_wall_seconds is not None and elapsed_seconds >= self.max_wall_seconds:
            return False
        if retries is not None and retries >= self.max_retries:
            return False
        if not self._quality_gates_pass(
            quality_gates_passed=quality_gates_passed,
            completed_quality_gates=completed_quality_gates,
            quality_gates=quality_gates,
        ):
            return False
        return True

    def _quality_gates_pass(
        self,
        *,
        quality_gates_passed: bool | None,
        completed_quality_gates: Iterable[str] | None,
        quality_gates: Mapping[str, Any] | None,
    ) -> bool:
        if quality_gates_passed is not None:
            return quality_gates_passed
        if completed_quality_gates is not None:
            completed = (
                {completed_quality_gates}
                if isinstance(completed_quality_gates, str)
                else set(completed_quality_gates)
            )
            return all(name in completed for name in self.quality_gate_names)
        if quality_gates is not None:
            return all(self._gate_value_passed(quality_gates.get(name)) for name in self.quality_gate_names)
        return True

    @staticmethod
    def _gate_value_passed(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().upper() in {"PASS", "PASSED", "OK", "SUCCESS", "TRUE"}
        return False

    @staticmethod
    def _resolve_alias(
        primary: int | float | None,
        alias: int | float | None,
        primary_name: str,
        alias_name: str,
    ) -> int | float | None:
        if primary is not None and alias is not None and primary != alias:
            raise ValueError(f"{primary_name} and {alias_name} disagree.")
        return primary if primary is not None else alias

    @staticmethod
    def _validate_counter(value: int | float, name: str) -> None:
        if value < 0:
            raise ValueError(f"{name} cannot be negative.")
