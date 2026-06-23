from dataclasses import dataclass

from localforge.models.domain import Task
from localforge.models.enums import FailureClass


@dataclass(frozen=True)
class CapabilityDecision:
    model_tier: str
    escalate: bool
    local_draft_allowed: bool
    rationale: str


class LocalWorkerCapabilityRouter:
    def route(
        self,
        task: Task,
        *,
        previous_failure_class: FailureClass | None = None,
    ) -> CapabilityDecision:
        reasons: list[str] = []
        risk = task.risk_level.lower()
        if risk in {"high", "critical"}:
            reasons.append(f"{risk} risk")
        allowed_files = _allowed_files(task)
        if len(allowed_files) > 2:
            reasons.append(f"{len(allowed_files)} contract files")
        text = f"{task.title} {task.description}".lower()
        if any(term in text for term in ("architecture", "public api", "cross-module")):
            reasons.append("architecture-sensitive scope")
        if previous_failure_class in {
            FailureClass.SEMANTIC_TEST_FAILURE,
            FailureClass.CONTRACT_DRIFT,
            FailureClass.PUBLIC_API_MISMATCH,
        }:
            reasons.append(f"{previous_failure_class.value.lower()} requires escalation")

        if reasons:
            return CapabilityDecision(
                model_tier="chief_engineer",
                escalate=True,
                local_draft_allowed=True,
                rationale="; ".join(reasons),
            )
        if risk == "medium":
            return CapabilityDecision(
                model_tier="local_medium",
                escalate=False,
                local_draft_allowed=False,
                rationale="medium bounded task within contract",
            )
        return CapabilityDecision(
            model_tier="local_small",
            escalate=False,
            local_draft_allowed=False,
            rationale="low-risk bounded task",
        )


def _allowed_files(task: Task) -> list[str]:
    contract = task.metadata.get("task_contract")
    if not isinstance(contract, dict):
        return []
    raw = contract.get("allowed_files")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]
