import asyncio
from typing import Any

import typer
from localforge.services.ci_sweeper_loop import CISweeperLoopService
from localforge.services.daily_triage_loop import DailyTriageLoopService
from localforge.services.eval_corpus import EvaluationCorpusService
from localforge.services.pr_babysitter_loop import PRBabysitterLoopService
from localforge.services.strategy_comparator import StrategyComparatorService
from rich.console import Console
from rich.table import Table

console = Console()
ops_loops_app = typer.Typer(help=("Manage and evaluate Phase 11 operational loops (L1 Triage, L2 CI Sweeper, L2 PR Babysitter) and strategy matrix."))


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@ops_loops_app.command("corpus")
def show_corpus() -> None:
    """Display the versioned evaluation corpus manifest and event stream (V6-1100)."""
    svc = EvaluationCorpusService()
    manifest = svc.get_manifest()
    events = svc.list_events()

    console.print(f"\n[bold]Evaluation Corpus v{manifest.corpus_version}[/bold] — Manifest Hash: [cyan]{manifest.manifest_hash[:12]}...[/cyan]")
    table = Table(title="Corpus Fixture Events")
    table.add_column("ID")
    table.add_column("Category")
    table.add_column("Title")
    table.add_column("Allowed Action")
    table.add_column("Hash")

    for e in events:
        table.add_row(e.id, e.category, e.title[:45], e.allowed_action, e.content_hash[:10])
    console.print(table)


@ops_loops_app.command("triage")
def run_triage(
    category: str | None = typer.Option(None, "--category", "-c"),
) -> None:
    """Run L1 Daily Project Triage report-only inspection (V6-1101)."""
    corpus_svc = EvaluationCorpusService()
    triage_svc = DailyTriageLoopService()

    events = corpus_svc.list_events(category)
    findings = triage_svc.run_cheap_triage(events)
    critique = triage_svc.generate_post_run_critique("cli_triage", findings)

    console.print(f"\n[bold]L1 Daily Project Triage Results ({len(findings)} items):[/bold]")
    table = Table(title="Triage Findings")
    table.add_column("ID")
    table.add_column("Priority")
    table.add_column("Classification")
    table.add_column("Recommended Action")
    table.add_column("Cost")

    for f in findings:
        color = "red" if f.priority == 1 else ("yellow" if f.priority == 2 else "gray")
        table.add_row(
            f.item_id,
            f"[{color}]{f.priority}[/{color}]",
            f.classification,
            f.recommended_action,
            f"${f.cost_usd:.4f}",
        )
    console.print(table)

    console.print(
        f"[cyan]Critique: verdict={critique.verdict} "
        f"actionable={critique.actionable_count} "
        f"noop={critique.noop_count} "
        f"cost=${critique.total_cost_usd:.4f}[/cyan]"
    )


@ops_loops_app.command("ci-sweeper")
def run_ci_sweeper(
    build_id: int = typer.Option(101, "--build-id", "-b"),
) -> None:
    """Run L2 CI Sweeper auto-repair on code regressions (V6-1102)."""
    corpus_svc = EvaluationCorpusService()
    sweeper_svc = CISweeperLoopService()

    events = corpus_svc.list_events()
    target_event = next(
        (e for e in events if e.payload.get("build_id") == build_id or e.id == f"EVT-00{build_id % 10}"),
        events[3],
    )

    classification = sweeper_svc.classify_ci_event(target_event)
    repair = sweeper_svc.execute_repair(classification)

    console.print(f"\n[bold]L2 CI Sweeper — Build {build_id}[/bold]")
    console.print(f"  Class: {classification.failure_class} | Can Auto-Fix: {classification.can_auto_fix}")
    console.print(f"  Status: [green]{repair.status}[/green] | Draft PR Created: {repair.draft_pr_created}")
    if repair.typed_evidence_summary:
        console.print(f"  Evidence: {repair.typed_evidence_summary}")


@ops_loops_app.command("pr-babysitter")
def run_pr_babysitter(
    pr_id: int = typer.Option(12, "--pr-id"),
    upstream_changed: bool = typer.Option(False, "--upstream-changed"),
) -> None:
    """Run L2 PR Babysitter for comment handling and worktree fixes (V6-1103)."""
    corpus_svc = EvaluationCorpusService()
    babysitter_svc = PRBabysitterLoopService()

    events = corpus_svc.list_events()
    target_event = next((e for e in events if e.payload.get("pr_id") == pr_id), events[6])

    action = babysitter_svc.process_pr_event(target_event, upstream_changed=upstream_changed)

    console.print(f"\n[bold]L2 PR Babysitter — PR #{pr_id}[/bold]")
    console.print(f"  Action Type: [green]{action.action_type}[/green]")
    console.print(f"  Summary: {action.summary}")


@ops_loops_app.command("compare")
def compare_strategies() -> None:
    """Run labeled corpus through 6 strategy combinations and evaluate gates (V6-1104, V6-1105)."""
    comparator = StrategyComparatorService()
    report = comparator.run_comparison_matrix()

    console.print(f"\n[bold]Strategy Comparison Matrix — Corpus v{report.corpus_version}[/bold]")

    table = Table(title="Strategy Performance Matrix")
    table.add_column("Strategy")
    table.add_column("PR_READY Rate")
    table.add_column("Recall")
    table.add_column("Duration")
    table.add_column("Tokens")
    table.add_column("Cost")
    table.add_column("Gate Verdict")

    for strat_name, met in report.metrics.items():
        gate = report.gate_results[strat_name]
        v_color = "green" if gate.verdict == "ACCEPTED" else "yellow"
        table.add_row(
            strat_name,
            f"{met.pr_ready_rate:.2f}",
            f"{met.classification_recall:.2f}",
            f"{met.execution_duration_ms:.1f}ms",
            f"{met.total_tokens:,}",
            f"${met.total_cost_usd:.4f}",
            f"[{v_color}]{gate.verdict}[/{v_color}]",
        )
    console.print(table)
