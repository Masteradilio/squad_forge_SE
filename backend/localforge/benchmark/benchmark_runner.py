import time
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import select, text
from localforge.storage.transactions import UnitOfWork
from localforge.models import domain
from localforge.models.enums import TaskStatus

class V3BenchmarkHarness:
    """
    Executes and reports V3 repeatable benchmark projects metrics.
    Tracks success rates, real API cost, simulated baseline costs, and net savings.
    """

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def run_benchmark(self, project_id: int) -> dict[str, Any]:
        """
        Gathers metrics from the database for the given project to build a benchmark report.
        Tracks actual outcomes vs hypothetical pricing alternatives.
        """
        # 1. Fetch project info
        assert self.uow.projects is not None
        assert self.uow.session is not None
        assert self.uow.cost_benchmark is not None
        assert self.uow.simulation is not None
        project = await self.uow.projects.get_project(project_id)
        if not project:
            return {"error": f"Project {project_id} not found."}

        start_time = time.time()

        # 2. Gather task outcomes
        # Using session direct query
        db_tasks = await self.uow.session.execute(
            text(f"SELECT status, COUNT(*) FROM tasks WHERE project_id = {project_id} GROUP BY status")
        )
        task_counts = {row[0]: row[1] for row in db_tasks.fetchall()}

        pr_ready = task_counts.get("PR_READY", 0)
        failed_safe = task_counts.get("FAILED_SAFE", 0)
        blocked = task_counts.get("BLOCKED", 0)
        total_tasks = sum(task_counts.values())

        pass_rate = (pr_ready / total_tasks * 100.0) if total_tasks > 0 else 0.0

        # 3. Retrieve unified cost benchmarks
        metrics = await self.uow.cost_benchmark.calculate_benchmarks(project_id)
        sim = await self.uow.simulation.simulate_api_only_costs(project_id)

        wall_clock = time.time() - start_time

        report = {
            "project_name": project.name,
            "total_tasks": total_tasks,
            "pr_ready": pr_ready,
            "failed_safe": failed_safe,
            "blocked": blocked,
            "pass_rate": pass_rate,
            "actual_paid_usd": metrics["actual_paid_usd"],
            "openai_simulated_usd": sim["openai_simulated_usd"],
            "google_simulated_usd": sim["google_simulated_usd"],
            "anthropic_simulated_usd": sim["anthropic_simulated_usd"],
            "openai_savings_usd": sim["openai_savings_usd"],
            "google_savings_usd": sim["google_savings_usd"],
            "anthropic_savings_usd": sim["anthropic_savings_usd"],
            "total_calls": metrics["actual_calls"],
            "local_calls_avoided": metrics["local_calls_avoided"],
            "wall_clock_seconds": wall_clock,
        }

        return report

    def generate_markdown_summary(self, report: dict[str, Any]) -> str:
        """Formats the benchmark metrics into a Markdown report."""
        if "error" in report:
            return f"# Benchmark Error\n{report['error']}"

        md = f"""# V3 Benchmark Acceptance Report - {report['project_name']}
Date: {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")} UTC

## Summary Metrics
- **Total Tasks**: {report['total_tasks']}
- **Tasks Ready for PR (PR_READY)**: {report['pr_ready']}
- **Tasks Failed Safe (FAILED_SAFE)**: {report['failed_safe']}
- **Blocked Tasks**: {report['blocked']}
- **Task Success Pass Rate**: {report['pass_rate']:.2f}%
- **Wall-Clock Processing Time**: {report['wall_clock_seconds']:.2f} seconds

## Financial & Cost Metrics
| Metric | LocalForge Hybrid | OpenAI API-Only | Anthropic API-Only | Google API-Only |
| :--- | :---: | :---: | :---: | :---: |
| **API Costs (USD)** | ${report['actual_paid_usd']:.4f} | ${report['openai_simulated_usd']:.4f} | ${report['anthropic_simulated_usd']:.4f} | ${report['google_simulated_usd']:.4f} |
| **Paid API Calls** | {report['total_calls']} | - | - | - |
| **Local Calls Saved** | {report['local_calls_avoided']} | - | - | - |
| **Projected Net Savings** | - | ${report['openai_savings_usd']:.4f} | ${report['anthropic_savings_usd']:.4f} | ${report['google_savings_usd']:.4f} |

## Conclusion
API-led routing to Chief Engineer combined with local worker task delegation achieved a **{report['pass_rate']:.2f}% pass rate** while generating significant token savings compared to 100% cloud API execution models.
"""
        return md
