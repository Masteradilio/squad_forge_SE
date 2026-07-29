from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkRunManifest:
    name: str
    task_count: int
    pr_ready_count: int
    failed_safe_count: int
    blocked_count: int
    human_interventions: int
    paid_calls: int
    estimated_cost_usd: float
    repair_attempts: int
    failure_classes: dict[str, int] = field(default_factory=dict)
    wall_clock_seconds: float = 0.0
    integration_passed: bool = False
    visual_passed: bool = False
    acceptance_scenarios_passed: int = 0
    acceptance_scenarios_total: int = 5


@dataclass(frozen=True)
class BenchmarkReport:
    rating: str
    markdown: str


class BenchmarkV2Reporter:
    def render(self, manifest: BenchmarkRunManifest) -> BenchmarkReport:
        rating = _rating(manifest)
        lines = [
            f"# LocalForge V2 Benchmark - {manifest.name}",
            "",
            f"rating: {rating}",
            f"task_count: {manifest.task_count}",
            f"pr_ready_count: {manifest.pr_ready_count}",
            f"failed_safe_count: {manifest.failed_safe_count}",
            f"blocked_count: {manifest.blocked_count}",
            f"human_interventions: {manifest.human_interventions}",
            f"paid_calls: {manifest.paid_calls}",
            f"estimated_cost_usd: {manifest.estimated_cost_usd:.6f}",
            f"repair_attempts: {manifest.repair_attempts}",
            f"wall_clock_seconds: {manifest.wall_clock_seconds:.1f}",
            f"integration_passed: {manifest.integration_passed}",
            f"visual_passed: {manifest.visual_passed}",
            (
                "acceptance_scenarios: "
                f"{manifest.acceptance_scenarios_passed}/{manifest.acceptance_scenarios_total}"
            ),
            "",
            "## Failure Classes",
        ]
        if manifest.failure_classes:
            lines.extend(
                f"- {name}: {count}" for name, count in sorted(manifest.failure_classes.items())
            )
        else:
            lines.append("- none")
        lines.append("")
        return BenchmarkReport(rating=rating, markdown="\n".join(lines))

    def write_report(self, manifest: BenchmarkRunManifest, output_path: str) -> BenchmarkReport:
        report = self.render(manifest)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.markdown, encoding="utf-8")
        return report


def _rating(manifest: BenchmarkRunManifest) -> str:
    all_scenarios = manifest.acceptance_scenarios_passed == manifest.acceptance_scenarios_total
    all_tasks_ready = (
        manifest.task_count > 0
        and manifest.pr_ready_count == manifest.task_count
        and manifest.failed_safe_count == 0
        and manifest.blocked_count == 0
    )
    if (
        all_scenarios
        and all_tasks_ready
        and manifest.integration_passed
        and manifest.visual_passed
        and manifest.human_interventions == 0
    ):
        return "Funciona bem"
    if manifest.pr_ready_count > 0 or manifest.failed_safe_count > 0:
        return "Funciona com ressalvas"
    return "Nao esta pronto"
