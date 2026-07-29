from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from localforge.services.ci_sweeper_loop import CISweeperLoopService
from localforge.services.daily_triage_loop import DailyTriageLoopService
from localforge.services.eval_corpus import EvaluationCorpusService
from localforge.services.pr_babysitter_loop import PRBabysitterLoopService
from localforge.services.strategy_comparator import (
    StrategyComparatorService,
    StrategyComparisonReport,
)

router = APIRouter(tags=["operational-loops"])


class TriageRunRequest(BaseModel):
    category_filter: str | None = None


class CISweeperRunRequest(BaseModel):
    build_id: int | str = 101


class PRBabysitterRunRequest(BaseModel):
    pr_id: int = 12
    upstream_changed: bool = False


# ─── Evaluation Corpus & Baselines (V6-1100) ──────────────────────────────── #


@router.get("/loops/eval-corpus/manifest")
async def get_eval_corpus_manifest() -> dict[str, Any]:
    """Get the versioned evaluation corpus manifest with SHA-256 hashes (V6-1100)."""
    svc = EvaluationCorpusService()
    return svc.get_manifest().model_dump(mode="json")


@router.get("/loops/eval-corpus/events")
async def list_eval_corpus_events(category: str | None = None) -> list[dict[str, Any]]:
    """List events in the evaluation corpus (V6-1100)."""
    svc = EvaluationCorpusService()
    return [e.model_dump(mode="json") for e in svc.list_events(category)]


# ─── Daily Project Triage Loop L1 (V6-1101) ────────────────────────────────── #


@router.post("/loops/triage/run")
async def run_daily_triage(req: TriageRunRequest) -> dict[str, Any]:
    """Run L1 Daily Project Triage — report-only cheap triage with zero LLM cost (V6-1101)."""
    corpus_svc = EvaluationCorpusService()
    triage_svc = DailyTriageLoopService()

    events = corpus_svc.list_events(req.category_filter)
    findings = triage_svc.run_cheap_triage(events)
    critique = triage_svc.generate_post_run_critique("triage_run_001", findings)

    return {
        "findings": [f.model_dump(mode="json") for f in findings],
        "critique": critique.model_dump(mode="json"),
    }


# ─── CI Sweeper Loop L2 (V6-1102) ──────────────────────────────────────────── #


@router.post("/loops/ci-sweeper/run")
async def run_ci_sweeper(req: CISweeperRunRequest) -> dict[str, Any]:
    """Run L2 CI Sweeper — failure classification, allowlisted auto-fix, draft PR (V6-1102)."""
    corpus_svc = EvaluationCorpusService()
    sweeper_svc = CISweeperLoopService()

    events = corpus_svc.list_events()
    target_event = next(
        (
            e
            for e in events
            if e.payload.get("build_id") == req.build_id or e.id == str(req.build_id)
        ),
        events[3],
    )

    classification = sweeper_svc.classify_ci_event(target_event)
    repair_result = sweeper_svc.execute_repair(classification)

    return {
        "classification": classification.model_dump(mode="json"),
        "repair_result": repair_result.model_dump(mode="json"),
    }


# ─── PR Babysitter Loop L2 (V6-1103) ───────────────────────────────────────── #


@router.post("/loops/pr-babysitter/run")
async def run_pr_babysitter(req: PRBabysitterRunRequest) -> dict[str, Any]:
    """Run L2 PR Babysitter — comment deduplication, isolated worktree fixes, upstream revalidation (V6-1103)."""
    corpus_svc = EvaluationCorpusService()
    babysitter_svc = PRBabysitterLoopService()

    events = corpus_svc.list_events()
    target_event = next((e for e in events if e.payload.get("pr_id") == req.pr_id), events[6])

    action = babysitter_svc.process_pr_event(target_event, upstream_changed=req.upstream_changed)

    return {
        "action": action.model_dump(mode="json"),
    }


# ─── Strategy Comparison Matrix & Gates (V6-1104, V6-1105, V6-1106) ──────── #


@router.post("/loops/compare-strategies")
async def compare_execution_strategies() -> StrategyComparisonReport:
    """Run labeled corpus through 6 strategy combinations and apply strategy gates (V6-1104, V6-1105)."""
    comparator = StrategyComparatorService()
    return comparator.run_comparison_matrix()
