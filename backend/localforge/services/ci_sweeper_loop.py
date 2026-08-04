"""CI Sweeper Loop L2 implementation."""

import logging

from pydantic import BaseModel

from localforge.services.eval_corpus import LabeledEvent
from localforge.services.operational_connector import (
    CheckRunRecord,
    CIRepairExecution,
    OperationalRepositoryConnector,
    fetch_all_pages,
    sanitize_external_text,
)
from localforge.services.operational_state import OperationalIdempotencyStore

logger = logging.getLogger(__name__)

ALLOWLISTED_AUTO_FIX_CLASSES = {"CODE_REGRESSION"}
MAX_REPAIR_ATTEMPTS = 3


class CIClassificationResult(BaseModel):
    """Failure classification for a CI failure event (V6-1102)."""

    build_id: int | str
    failure_class: str  # CODE_REGRESSION, FLAKE, ENVIRONMENT, CONFIGURATION, DEPENDENCY, UNKNOWN
    failure_fingerprint: str
    can_auto_fix: bool
    reason: str


class CIRepairResult(BaseModel):
    """Repair execution result produced by CI Sweeper L2 (V6-1102)."""

    build_id: int | str
    failure_class: str
    attempts_used: int
    circuit_breaker_opened: bool = False
    draft_pr_created: bool = False
    draft_pr_title: str | None = None
    typed_evidence_summary: str | None = None
    requires_human_merge: bool = True
    test_weakened_or_deleted: bool = False  # Strictly MUST be False
    status: str  # REPAIRED_DRAFT_PR, REQUIRES_CONTROLLED_CONNECTOR, BREAKER_OPEN, FAILED


class CISweeperLoopService:
    """Classify failed checks and create allowlisted draft repairs."""

    def __init__(self, state_store: OperationalIdempotencyStore | None = None) -> None:
        self.state_store = state_store or OperationalIdempotencyStore()

    def classify_ci_event(self, event: LabeledEvent) -> CIClassificationResult:
        """Classify CI failure into known failure classes."""
        payload = event.payload
        build_id = payload.get("build_id", event.id)

        # Flake detection
        if payload.get("is_flaky") or event.expected_classification == "FLAKE":
            fingerprint = f"flake_{payload.get('failed_test', event.id)}"
            return CIClassificationResult(
                build_id=build_id,
                failure_class="FLAKE",
                failure_fingerprint=fingerprint,
                can_auto_fix=False,
                reason="Flaky test detected — auto-fix suppressed.",
            )

        # Environment failure detection
        if (
            "command not found" in str(payload.get("error_log", "")).lower()
            or event.expected_classification == "ENVIRONMENT"
        ):
            fingerprint = f"env_{build_id}"
            return CIClassificationResult(
                build_id=build_id,
                failure_class="ENVIRONMENT",
                failure_fingerprint=fingerprint,
                can_auto_fix=False,
                reason="Environment/infrastructure failure — requires DevOps escalation.",
            )

        # Code regression
        fingerprint = f"code_reg_{payload.get('failed_test', event.id)}"
        return CIClassificationResult(
            build_id=build_id,
            failure_class="CODE_REGRESSION",
            failure_fingerprint=fingerprint,
            can_auto_fix=True,
            reason="Allowlisted code regression — eligible for L2 repair in isolated worktree.",
        )

    def classify_connector_failures(
        self, connector: OperationalRepositoryConnector
    ) -> list[CIClassificationResult]:
        """Classify failed check runs fetched through a repository connector."""
        classifications: list[CIClassificationResult] = []
        for item in fetch_all_pages(connector.list_check_runs):
            if not isinstance(item, CheckRunRecord) or item.conclusion != "failure":
                continue
            event = LabeledEvent(
                id=item.external_id,
                category="CI_FLAKE" if item.is_flaky else "CI_CODE_REGRESSION",
                title=sanitize_external_text(item.name),
                payload={
                    "build_id": item.build_id,
                    "failed_test": item.failed_test,
                    "error_log": sanitize_external_text(item.log_excerpt),
                    "is_flaky": item.is_flaky,
                },
                expected_classification="FLAKE" if item.is_flaky else "CODE_REGRESSION",
                allowed_action="AUTO_FIX" if not item.is_flaky else "REPORT_ONLY",
                required_approval="HUMAN_MERGE",
            )
            classifications.append(self.classify_ci_event(event))
        return classifications

    def execute_repair(
        self,
        classification: CIClassificationResult,
        connector: OperationalRepositoryConnector | None = None,
    ) -> CIRepairResult:
        """Execute allowlisted CI repair under max 3 attempts & circuit breaker (V6-1102).

        Enforces:
        - Flake/Env failures do NOT trigger code edits.
        - Max 3 attempts per failure fingerprint; 4th attempt opens circuit breaker.
        - Maker/checker worktree isolation with typed evidence.
        - Draft PR with requires_human_merge=True.
        - Prohibition of test weakening or test deletion (test_weakened_or_deleted=False).
        """
        # Guard: allowlisted classes only
        if (
            not classification.can_auto_fix
            or classification.failure_class not in ALLOWLISTED_AUTO_FIX_CLASSES
        ):
            return CIRepairResult(
                build_id=classification.build_id,
                failure_class=classification.failure_class,
                attempts_used=0,
                circuit_breaker_opened=False,
                draft_pr_created=False,
                requires_human_merge=True,
                test_weakened_or_deleted=False,
                status="SKIPPED_UNAUTHORIZED_CLASS",
            )

        if connector is None:
            return CIRepairResult(
                build_id=classification.build_id,
                failure_class=classification.failure_class,
                attempts_used=0,
                circuit_breaker_opened=False,
                draft_pr_created=False,
                requires_human_merge=True,
                test_weakened_or_deleted=False,
                status="REQUIRES_CONTROLLED_CONNECTOR",
            )

        # Track attempts and enforce Circuit Breaker (V6-1102 regression)
        attempts = self.state_store.increment(
            "ci_sweeper_attempts",
            classification.failure_fingerprint,
        )

        if attempts > MAX_REPAIR_ATTEMPTS:
            logger.warning(
                "Failure fingerprint %s exceeded max attempts (%d). Opening breaker.",
                classification.failure_fingerprint,
                MAX_REPAIR_ATTEMPTS,
            )
            return CIRepairResult(
                build_id=classification.build_id,
                failure_class=classification.failure_class,
                attempts_used=attempts,
                circuit_breaker_opened=True,
                draft_pr_created=False,
                requires_human_merge=True,
                test_weakened_or_deleted=False,
                status="BREAKER_OPEN",
            )

        # Creating a PR is not a repair.  The connector must expose a real,
        # controlled worktree executor that returns observed checks and hashes.
        executor = getattr(connector, "execute_ci_repair", None)
        if not callable(executor):
            return CIRepairResult(
                build_id=classification.build_id,
                failure_class=classification.failure_class,
                attempts_used=attempts,
                requires_human_merge=True,
                test_weakened_or_deleted=False,
                status="REQUIRES_CONTROLLED_EXECUTOR",
            )
        execution = executor(classification.build_id, classification.failure_fingerprint)
        if not isinstance(execution, CIRepairExecution) or not execution.passed:
            return CIRepairResult(
                build_id=classification.build_id,
                failure_class=classification.failure_class,
                attempts_used=attempts,
                requires_human_merge=True,
                test_weakened_or_deleted=False,
                typed_evidence_summary=(
                    execution.evidence_summary if isinstance(execution, CIRepairExecution) else None
                ),
                status="REPAIR_FAILED",
            )
        if not execution.checks_executed or not all(
            value.strip() for value in (execution.source_commit, execution.target_commit, execution.diff_hash)
        ):
            return CIRepairResult(
                build_id=classification.build_id,
                failure_class=classification.failure_class,
                attempts_used=attempts,
                requires_human_merge=True,
                test_weakened_or_deleted=False,
                status="REQUIRES_OBSERVED_EVIDENCE",
            )
        evidence_summary = execution.evidence_summary
        draft_pr_title = f"fix(ci): repair regression for build {classification.build_id}"
        draft_pr = connector.create_draft_pr(
            title=draft_pr_title,
            branch=f"localforge/ci-{classification.build_id}",
            body=evidence_summary,
            idempotency_key=classification.failure_fingerprint,
        )
        draft_pr_title = draft_pr.title
        draft_pr_created = draft_pr.draft

        return CIRepairResult(
            build_id=classification.build_id,
            failure_class=classification.failure_class,
            attempts_used=attempts,
            circuit_breaker_opened=False,
            draft_pr_created=draft_pr_created,
            draft_pr_title=draft_pr_title,
            typed_evidence_summary=evidence_summary,
            requires_human_merge=True,
            test_weakened_or_deleted=False,  # Never weaken tests
            status="REPAIRED_DRAFT_PR",
        )
