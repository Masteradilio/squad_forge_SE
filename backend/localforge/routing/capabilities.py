from dataclasses import dataclass
from datetime import UTC, datetime

from localforge.models.domain import Task
from localforge.models.enums import FailureClass, TaskSeniorityClass
from localforge.storage.orm import ModelCapabilityORM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CapabilityDecision:
    model_tier: str
    escalate: bool
    local_draft_allowed: bool
    rationale: str
    seniority_class: TaskSeniorityClass


class TaskSeniorityClassifier:
    def classify(
        self,
        task: Task,
        *,
        previous_failures: list[FailureClass] | None = None,
    ) -> TaskSeniorityClass:
        contract = task.metadata.get("task_contract", {}) if isinstance(task.metadata, dict) else {}
        explicit_seniority = contract.get("seniority_class") if isinstance(contract, dict) else None
        if isinstance(explicit_seniority, str):
            try:
                return TaskSeniorityClass(explicit_seniority)
            except ValueError:
                pass

        # 1. UI and Visual tasks require chief engineer
        visual_required = contract.get("visual_required", False)
        if visual_required:
            return TaskSeniorityClass.CHIEF_ONLY

        # 2. Tasks with multiple allowed files
        allowed_files = _allowed_files(task)
        if len(allowed_files) > 5:
            return TaskSeniorityClass.CHIEF_ONLY
        elif len(allowed_files) > 2:
            return TaskSeniorityClass.CHIEF_LED

        # 3. Critical errors or architecture sensitive scope
        text = f"{task.title} {task.description}".lower()
        if any(
            term in text
            for term in ("architecture", "public api", "cross-module", "breaking change")
        ):
            return TaskSeniorityClass.CHIEF_ONLY

        # 4. Enforce escalation for previous failures
        if previous_failures:
            # Se houver falhas repetidas ou falhas graves de timeout, drift e api mismatch
            if any(
                f
                in {
                    FailureClass.TIMEOUT,
                    FailureClass.CONTRACT_DRIFT,
                    FailureClass.PUBLIC_API_MISMATCH,
                }
                for f in previous_failures
            ):
                return TaskSeniorityClass.CHIEF_ONLY
            if len(previous_failures) >= 2:
                return TaskSeniorityClass.CHIEF_ONLY

        # 5. Bounded lanes
        risk = task.risk_level.lower()
        if risk in {"high", "critical"}:
            return TaskSeniorityClass.CHIEF_LED

        # 6. Simple documentation
        if any(term in text for term in ("documentation", "changelog", "readme", "summary")):
            return TaskSeniorityClass.LOCAL_ONLY

        # 7. Default lane
        return TaskSeniorityClass.LOCAL_ASSISTED


class LocalWorkerCapabilityRouter:
    def __init__(self, session: AsyncSession | None = None):
        self.session = session
        self.classifier = TaskSeniorityClassifier()

    async def route(
        self,
        task: Task,
        *,
        previous_failures: list[FailureClass] | None = None,
        model_name: str | None = None,
        previous_failure_class: FailureClass | None = None,
    ) -> CapabilityDecision:
        if previous_failure_class and not previous_failures:
            previous_failures = [previous_failure_class]

        seniority = self.classifier.classify(task, previous_failures=previous_failures)
        reasons: list[str] = [f"Classified as {seniority.value}"]

        # Check model capability and disqualification markers in DB if session is active
        if self.session and model_name:
            result = await self.session.execute(
                select(ModelCapabilityORM).where(
                    ModelCapabilityORM.model_name == model_name,
                    ModelCapabilityORM.task_class == seniority.value,
                )
            )
            orm_cap = result.scalar_one_or_none()

            if orm_cap:
                disq = orm_cap.disqualified_until
                if disq and (disq if disq.tzinfo else disq.replace(tzinfo=UTC)) > datetime.now(UTC):
                    reasons.append(
                        f"Model {model_name} is disqualified: {orm_cap.disqualification_reason}"
                    )
                    return CapabilityDecision(
                        model_tier="chief_engineer",
                        escalate=True,
                        local_draft_allowed=False,
                        rationale="; ".join(reasons),
                        seniority_class=TaskSeniorityClass.CHIEF_ONLY,
                    )

        if seniority == TaskSeniorityClass.CHIEF_ONLY:
            return CapabilityDecision(
                model_tier="chief_engineer",
                escalate=True,
                local_draft_allowed=False,
                rationale="; ".join(reasons),
                seniority_class=seniority,
            )
        elif seniority == TaskSeniorityClass.CHIEF_LED:
            return CapabilityDecision(
                model_tier="chief_engineer",
                escalate=True,
                local_draft_allowed=True,
                rationale="; ".join(reasons),
                seniority_class=seniority,
            )
        elif seniority == TaskSeniorityClass.LOCAL_ASSISTED:
            return CapabilityDecision(
                model_tier="local_medium",
                escalate=False,
                local_draft_allowed=False,
                rationale="; ".join(reasons),
                seniority_class=seniority,
            )
        else:  # LOCAL_ONLY / DETERMINISTIC_ONLY
            return CapabilityDecision(
                model_tier="local_small",
                escalate=False,
                local_draft_allowed=False,
                rationale="; ".join(reasons),
                seniority_class=seniority,
            )


def _allowed_files(task: Task) -> list[str]:
    contract = task.metadata.get("task_contract")
    if not isinstance(contract, dict):
        return []
    raw = contract.get("allowed_files")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]
