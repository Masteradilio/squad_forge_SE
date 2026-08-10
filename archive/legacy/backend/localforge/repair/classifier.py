from dataclasses import dataclass
from typing import Any

from localforge.models.enums import FailureClass


@dataclass(frozen=True)
class ClassifiedFailure:
    failure_class: FailureClass
    playbook: str
    escalate_to_chief: bool


class FailureClassifier:
    def classify(
        self,
        *,
        output: str,
        task_contract: dict[str, Any],
        attempt_count: int,
    ) -> ClassifiedFailure:
        text = output.lower()
        if "syntaxerror" in text:
            return ClassifiedFailure(
                FailureClass.SYNTAX_ERROR,
                "Run Python syntax verifier and request a minimal local syntax patch.",
                False,
            )
        if "modulenotfounderror" in text or "importerror" in text:
            return ClassifiedFailure(
                FailureClass.MISSING_IMPORT,
                "Check the approved module map and repair imports within allowed files.",
                False,
            )
        if "forbidden dependency" in text or "undeclared dependency" in text:
            return ClassifiedFailure(
                FailureClass.FORBIDDEN_DEPENDENCY,
                "Replace undeclared dependency usage with dependency-free implementation.",
                False,
            )
        if "timed out" in text or "timeout" in text:
            return ClassifiedFailure(
                FailureClass.TIMEOUT,
                "Reduce command scope and inspect the smallest reproducible timeout.",
                attempt_count >= 2,
            )
        if attempt_count >= 2:
            return ClassifiedFailure(
                FailureClass.SEMANTIC_TEST_FAILURE,
                "Escalate compact failing evidence for semantic repair planning.",
                True,
            )
        if not task_contract.get("allowed_files"):
            return ClassifiedFailure(
                FailureClass.CONTRACT_DRIFT,
                "Stop execution until the task has an explicit contract packet.",
                True,
            )
        return ClassifiedFailure(
            FailureClass.SEMANTIC_TEST_FAILURE,
            "Run targeted local repair against failing assertion only.",
            False,
        )
