from dataclasses import dataclass, field

from localforge.healing.classifier import FailureClass


@dataclass(frozen=True)
class RepairPolicyDecision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class RepairPolicyState:
    attempt_count: int = 0
    seen_failures: tuple[FailureClass, ...] = field(default_factory=tuple)
    diff_growth: int = 0

    def record(self, failure_class: FailureClass, diff_growth: int) -> "RepairPolicyState":
        return RepairPolicyState(
            attempt_count=self.attempt_count + 1,
            seen_failures=(*self.seen_failures, failure_class),
            diff_growth=self.diff_growth + diff_growth,
        )


@dataclass(frozen=True)
class RepairPolicy:
    max_attempts: int = 3
    max_diff_growth: int = 500

    def can_attempt(
        self,
        state: RepairPolicyState,
        failure_class: FailureClass,
        diff_growth: int,
    ) -> RepairPolicyDecision:
        if state.attempt_count >= self.max_attempts:
            return RepairPolicyDecision(False, "max repair attempts reached")
        if state.seen_failures and state.seen_failures[-1] == failure_class:
            return RepairPolicyDecision(False, "same failure repeated")
        if state.diff_growth + diff_growth > self.max_diff_growth:
            return RepairPolicyDecision(False, "diff growth limit exceeded")
        if failure_class == FailureClass.COMMAND_BLOCKED_BY_POLICY:
            return RepairPolicyDecision(False, "safety denial")
        return RepairPolicyDecision(True)
