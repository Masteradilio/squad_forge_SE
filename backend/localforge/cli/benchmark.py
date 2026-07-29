import asyncio
import os

import typer
from localforge.benchmark.benchmark_runner import V3BenchmarkHarness
from localforge.storage import UnitOfWork
from rich.console import Console

benchmark_app = typer.Typer(help="Manage and execute V3 repeatable benchmarks.")


@benchmark_app.command("report")
def benchmark_report_cmd(
    project_id: int = typer.Option(1, "--project-id", help="Project ID for the benchmark."),
):
    """Generate a V3 Benchmark Acceptance Report for a project."""
    console = Console()

    async def run():
        async with UnitOfWork() as uow:
            harness = V3BenchmarkHarness(uow)
            report = await harness.run_benchmark(project_id)
            if "error" in report:
                console.print(f"[red]Error: {report['error']}[/red]")
                return

            md_summary = harness.generate_markdown_summary(report)
            console.print("\n[bold green]=== V3 Benchmark Acceptance Summary ===[/bold green]\n")
            console.print(md_summary)

            # Write to disk
            report_path = "docs/benchmark_report.md"
            os.makedirs("docs", exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(md_summary)
            console.print(f"\n[green]Report successfully saved to {report_path}[/green]")

    asyncio.run(run())
