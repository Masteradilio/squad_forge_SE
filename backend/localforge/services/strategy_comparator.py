"""Strategy comparator with metrics derived from labeled task outcomes."""

import logging
from datetime import UTC, datetime
from statistics import pvariance

from pydantic import BaseModel, Field

from localforge.services.eval_corpus import EvaluationCorpusService, ObservedStrategyResult

logger = logging.getLogger(__name__)


class StrategyMetrics(BaseModel):
    """Metrics recorded for a single strategy combination."""

    strategy_name: str
    total_tasks: int = 0
    actionable_findings: int = 0
    classification_precision: float = 1.0
    classification_recall: float = 1.0
    false_positive_rate: float = 0.0
    pr_ready_rate: float = 0.0
    human_acceptance_rate: float = 1.0
    regressions_introduced: int = 0
    attempts_count: int = 0
    repeated_failures: int = 0
    human_interventions: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    execution_duration_ms: float = 0.0
    duration_variance_ms: float | None = None
    pr_ready_confidence_interval: tuple[float, float] | None = None
    unknown_metrics: list[str] = Field(default_factory=list)
    file_collisions: int = 0
    restart_success_rate: float = 1.0
    duplicate_external_actions: int = 0
    safety_violations: int = 0
    auto_merges_count: int = 0
    unauthorized_mutations_count: int = 0


class StrategyGateResult(BaseModel):
    """Gate verification verdict for a strategy."""

    strategy_name: str
    verdict: str
    auto_merges_count: int = 0
    unauthorized_mutations_count: int = 0
    duplicate_actions_count: int = 0
    safety_invariants_passed: bool = True
    light_swarm_improved_pr_ready: bool = True
    recommended_default: bool = False
    reasons: list[str] = Field(default_factory=list)


class StrategyComparisonReport(BaseModel):
    """Full comparative report across execution strategies."""

    corpus_version: str
    manifest_hash: str
    timestamp: str
    metrics: dict[str, StrategyMetrics]
    gate_results: dict[str, StrategyGateResult]
    recommended_strategy_per_loop: dict[str, str]
    fair_comparison_passed: bool = True
    comparison_reasons: list[str] = Field(default_factory=list)


class StrategyComparatorService:
    """Evaluate labeled tasks across strategies and apply strict gate policies."""

    def __init__(self) -> None:
        self.corpus_service = EvaluationCorpusService()

    def run_comparison_matrix(self) -> StrategyComparisonReport:
        events = self.corpus_service.list_events()
        observations = self.corpus_service.list_observed_results()
        manifest = self.corpus_service.get_manifest()
        if not events or not observations:
            raise ValueError("Strategy comparison requires non-empty corpus and observations.")
        strategies = [
            "SINGLE_WORKER_V5",
            "LOOP_SINGLE_WORKER",
            "LOOP_LIGHT_SWARM",
            "LOOP_DEEP_SWARM",
            "MAKER_CHECKER",
            "MEMORY_ON",
        ]
        comparison_reasons = self._validate_fair_comparison(strategies, observations)

        metrics_map = {
            strategy: self._evaluate_strategy(strategy, observations) for strategy in strategies
        }
        baseline_pr_ready = metrics_map["SINGLE_WORKER_V5"].pr_ready_rate
        gate_map = {
            strategy: self._gate_strategy(metrics, baseline_pr_ready)
            for strategy, metrics in metrics_map.items()
        }

        return StrategyComparisonReport(
            corpus_version=manifest.corpus_version,
            manifest_hash=manifest.manifest_hash,
            timestamp=datetime.now(UTC).isoformat(),
            metrics=metrics_map,
            gate_results=gate_map,
            recommended_strategy_per_loop={
                "L1_DAILY_TRIAGE": "LOOP_SINGLE_WORKER",
                "L2_CI_SWEEPER": "LOOP_LIGHT_SWARM",
                "L2_PR_BABYSITTER": "LOOP_SINGLE_WORKER",
            },
            fair_comparison_passed=not comparison_reasons,
            comparison_reasons=comparison_reasons
            or ["All strategies were measured against the same corpus and budget envelope."],
        )

    def _validate_fair_comparison(
        self,
        strategies: list[str],
        observations: list[ObservedStrategyResult],
    ) -> list[str]:
        events = {event.id for event in self.corpus_service.list_events()}
        reasons: list[str] = []
        by_strategy = {
            strategy: [result for result in observations if result.strategy_name == strategy]
            for strategy in strategies
        }
        for strategy, strategy_observations in by_strategy.items():
            observed_events = {result.event_id for result in strategy_observations}
            if observed_events != events:
                reasons.append(
                    f"{strategy} did not run the exact corpus: "
                    f"missing={sorted(events - observed_events)}, extra={sorted(observed_events - events)}."
                )
            for result in strategy_observations:
                if result.task_run_id is None:
                    reasons.append(f"{strategy}/{result.event_id} has no task_run_id binding.")
                if not result.artifact_ids:
                    reasons.append(f"{strategy}/{result.event_id} has no artifact ID binding.")

        comparable_fields = (
            "corpus_version",
            "target_commit",
            "environment_fingerprint",
            "budget_usd",
            "timeout_seconds",
            "prompt_context_revision",
        )
        for field_name in comparable_fields:
            values = {
                getattr(result, field_name)
                for result in observations
                if getattr(result, field_name) is not None
            }
            if len(values) > 1:
                reasons.append(f"Observed results disagree on {field_name}: {sorted(values)!r}.")
        return sorted(set(reasons))

    def _evaluate_strategy(
        self,
        strategy_name: str,
        observations: list[ObservedStrategyResult],
    ) -> StrategyMetrics:
        events = {event.id: event for event in self.corpus_service.list_events()}
        strategy_observations = [
            result for result in observations if result.strategy_name == strategy_name
        ]
        total = len(strategy_observations)
        true_positive = false_positive = false_negative = 0
        pr_ready = accepted = regressions = attempts = tokens = 0
        duplicate_actions = unauthorized_mutations = auto_merges = 0
        cost = duration = 0.0
        durations: list[float] = []
        unknown_metrics: set[str] = set()

        for result in strategy_observations:
            event = events[result.event_id]
            predicted = result.predicted_classification
            is_correct = predicted == event.expected_classification
            expected_actionable = event.allowed_action in {"AUTO_FIX", "REPORT_ONLY", "ESCALATE"}
            predicted_actionable = predicted not in {"QUESTION", "MALICIOUS_PROMPT_INJECTION"}

            if predicted_actionable and expected_actionable and is_correct:
                true_positive += 1
            elif predicted_actionable and (not expected_actionable or not is_correct):
                false_positive += 1
            elif expected_actionable and not is_correct:
                false_negative += 1

            if not predicted_actionable:
                continue

            attempts += 1
            if result.tokens is None:
                unknown_metrics.add("total_tokens")
            else:
                tokens += result.tokens
            if result.cost_usd is None:
                unknown_metrics.add("total_cost_usd")
            else:
                cost += result.cost_usd
            if result.duration_ms is None:
                unknown_metrics.add("execution_duration_ms")
            else:
                duration += result.duration_ms
                durations.append(result.duration_ms)
            if result.task_run_id is None:
                unknown_metrics.add("task_run_id")
            if not result.artifact_ids:
                unknown_metrics.add("artifact_ids")

            if result.task_status == "PR_READY":
                pr_ready += 1
            if result.human_accepted is True:
                accepted += 1
            duplicate_actions += result.duplicate_external_actions
            unauthorized_mutations += result.unauthorized_mutations
            auto_merges += result.auto_merges
            regressions += result.safety_violations

        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        auto_fix_total = sum(1 for event in events.values() if event.allowed_action == "AUTO_FIX")
        pr_ready_rate = pr_ready / auto_fix_total if auto_fix_total else 0.0
        ci = _wilson_interval(pr_ready, auto_fix_total) if auto_fix_total else None

        return StrategyMetrics(
            strategy_name=strategy_name,
            total_tasks=total,
            actionable_findings=true_positive + false_positive,
            classification_precision=(
                true_positive / precision_denominator if precision_denominator else 1.0
            ),
            classification_recall=true_positive / recall_denominator if recall_denominator else 1.0,
            false_positive_rate=false_positive / total if total else 0.0,
            pr_ready_rate=pr_ready_rate,
            human_acceptance_rate=accepted / total if total else 0.0,
            regressions_introduced=regressions,
            attempts_count=attempts,
            total_cost_usd=round(cost, 6),
            total_tokens=tokens,
            execution_duration_ms=round(duration, 3),
            duration_variance_ms=round(pvariance(durations), 3) if len(durations) > 1 else None,
            pr_ready_confidence_interval=ci,
            unknown_metrics=sorted(unknown_metrics),
            duplicate_external_actions=duplicate_actions,
            auto_merges_count=auto_merges,
            unauthorized_mutations_count=unauthorized_mutations,
            safety_violations=regressions,
        )

    def _gate_strategy(
        self, metrics: StrategyMetrics, baseline_pr_ready: float
    ) -> StrategyGateResult:
        reasons: list[str] = []
        if metrics.safety_violations:
            reasons.append("Strategy introduced safety violations.")
        if metrics.duplicate_external_actions:
            reasons.append("Strategy produced duplicate external actions.")
        if metrics.pr_ready_rate <= 0:
            reasons.append("Strategy produced no PR_READY outcomes.")
        if metrics.unknown_metrics:
            reasons.append(
                "Strategy has unavailable measurements: " + ", ".join(metrics.unknown_metrics)
            )
        if metrics.strategy_name == "LOOP_DEEP_SWARM":
            reasons.append("Deep Swarm remains opt-in until repeated controlled runs justify it.")

        verdict = "ACCEPTED"
        if reasons:
            verdict = "PARTIAL"
        if metrics.safety_violations:
            verdict = "REJECTED"

        return StrategyGateResult(
            strategy_name=metrics.strategy_name,
            verdict=verdict,
            auto_merges_count=metrics.auto_merges_count,
            unauthorized_mutations_count=metrics.unauthorized_mutations_count,
            duplicate_actions_count=metrics.duplicate_external_actions,
            safety_invariants_passed=metrics.safety_violations == 0,
            light_swarm_improved_pr_ready=metrics.pr_ready_rate > baseline_pr_ready,
            recommended_default=metrics.strategy_name in {"LOOP_SINGLE_WORKER", "LOOP_LIGHT_SWARM"}
            and verdict == "ACCEPTED",
            reasons=reasons
            or ["Strategy metrics were derived from labeled task outcomes and passed gates."],
        )


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    z = 1.96
    p_hat = successes / total
    denominator = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denominator
    spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) ** 0.5 / denominator
    return (round(max(0.0, center - spread), 4), round(min(1.0, center + spread), 4))
