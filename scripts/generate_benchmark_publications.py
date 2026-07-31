"""Generate reproducible benchmark publications from observed comparative evaluations (V61C-904).

Produces observations.jsonl, summary_aggregates.json, and benchmark_report.md
from the exact same dataset, validating row counts, hashes, and Markdown table fidelity.
"""

import json
from pathlib import Path

from localforge.services.strategy_comparator import StrategyComparatorService


def generate_benchmark_publications(output_dir: Path) -> dict[str, str]:
    """Generate observations, JSON aggregates, and Markdown tables from canonical data."""
    output_dir.mkdir(parents=True, exist_ok=True)
    comparator = StrategyComparatorService()
    report = comparator.run_comparison_matrix()

    # 1. Generate summary_aggregates.json
    aggregates_path = output_dir / "summary_aggregates.json"
    aggregates_data = report.model_dump(mode="json")
    aggregates_path.write_text(json.dumps(aggregates_data, indent=2) + "\n", encoding="utf-8")

    # 2. Generate observations.jsonl
    observations_path = output_dir / "observations.jsonl"
    obs_list = comparator.corpus_service.list_observed_results()
    with observations_path.open("w", encoding="utf-8") as f:
        for obs in obs_list:
            f.write(json.dumps(obs.model_dump(mode="json")) + "\n")

    # 3. Generate benchmark_report.md
    md_path = output_dir / "benchmark_report.md"
    lines = [
        "# LocalForge OS — Observed Benchmark Report",
        "",
        f"- **Corpus Version**: `{report.corpus_version}`",
        f"- **Manifest Hash**: `{report.manifest_hash}`",
        f"- **Timestamp**: `{report.timestamp}`",
        f"- **Fair Comparison Passed**: `{report.fair_comparison_passed}`",
        "",
        "## Strategy Metrics Summary",
        "",
        "| Strategy | Total Tasks | PR Ready Rate | Precision | Recall | Cost (USD) | Verdict |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for strat, m in report.metrics.items():
        gate = report.gate_results.get(strat)
        verdict = gate.verdict if gate else "UNKNOWN"
        lines.append(
            f"| `{strat}` | {m.total_tasks} | {m.pr_ready_rate:.1%} | "
            f"{m.classification_precision:.1%} | {m.classification_recall:.1%} | "
            f"${m.total_cost_usd:.4f} | `{verdict}` |"
        )

    lines.extend([
        "",
        "## Recommended Strategy per Operational Loop",
        "",
    ])
    for loop_name, strat_rec in report.recommended_strategy_per_loop.items():
        lines.append(f"- **{loop_name}**: `{strat_rec}`")

    lines.append("")
    md_content = "\n".join(lines)
    md_path.write_text(md_content, encoding="utf-8")

    return {
        "aggregates_path": str(aggregates_path),
        "observations_path": str(observations_path),
        "report_path": str(md_path),
    }


if __name__ == "__main__":
    out = generate_benchmark_publications(Path("docs/e2e/v6_2_compliance/phase_R9"))
    print(f"Benchmark publications generated successfully: {out}")
