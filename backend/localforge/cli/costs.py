import asyncio
import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from localforge.storage import UnitOfWork

costs_app = typer.Typer(help="Manage and view LocalForge token costs and savings benchmarks.")
costs_sources_app = typer.Typer(help="View configured competitor pricing sources.")
costs_app.add_typer(costs_sources_app, name="sources")


@costs_sources_app.command("list")
def list_pricing_sources_cmd():
    """List all competitor pricing sources and snapshots from database."""
    console = Console()
    
    async def run():
        async with UnitOfWork() as uow:
            sources = await uow.model_calls.list_pricing_sources()
            snapshots = await uow.model_calls.list_pricing_snapshots()
            
            if not sources:
                console.print("[yellow]No pricing sources found in the database. Please bootstrap first.[/yellow]")
                return
                
            console.print("\n[bold green]=== Competitor Pricing Sources ===[/bold green]")
            table_sources = Table(title="Pricing Sources")
            table_sources.add_column("ID", justify="right")
            table_sources.add_column("Provider", style="cyan")
            table_sources.add_column("URL", style="blue")
            table_sources.add_column("Retrieved At", style="magenta")
            
            for s in sources:
                table_sources.add_row(
                    str(s.id),
                    s.provider,
                    s.url,
                    s.retrieved_at.strftime("%Y-%m-%d %H:%M:%S")
                )
            console.print(table_sources)
            
            console.print("\n[bold green]=== Model Pricing Snapshots (Per 1M Tokens) ===[/bold green]")
            table_snaps = Table(title="Pricing Snapshots")
            table_snaps.add_column("Model Name", style="cyan")
            table_snaps.add_column("Input Price (USD)", justify="right")
            table_snaps.add_column("Output Price (USD)", justify="right")
            table_snaps.add_column("Cached Input Price (USD)", justify="right")
            
            for snap in snapshots:
                table_snaps.add_row(
                    snap.model_name,
                    f"${snap.input_price_per_million:.2f}",
                    f"${snap.output_price_per_million:.2f}",
                    f"${snap.cached_input_price_per_million:.2f}"
                )
            console.print(table_snaps)

    asyncio.run(run())


@costs_sources_app.command("add")
def add_pricing_source_cmd(
    provider: str = typer.Option(..., "--provider", help="Name of the pricing provider (e.g. OpenAI)."),
    url: str = typer.Option(..., "--url", help="Official pricing URL."),
    notes: str = typer.Option("", "--notes", help="Optional notes about the pricing retrieval."),
):
    """Add a new competitor pricing source to the database."""
    console = Console()
    async def run():
        async with UnitOfWork() as uow:
            from localforge.models.domain import PricingSource
            source = await uow.model_calls.create_pricing_source(
                PricingSource(provider=provider, url=url, notes=notes)
            )
            console.print(f"[bold green]Successfully added pricing source #{source.id} for {source.provider}.[/bold green]")
    asyncio.run(run())


@costs_app.command("update-price")
def update_price_cmd(
    source_id: int = typer.Option(..., "--source-id", help="Database ID of the pricing source."),
    model: str = typer.Option(..., "--model", help="Competitor model name (e.g. gpt-5.5-large)."),
    input_price: float = typer.Option(..., "--input", help="Price per million input tokens in USD."),
    output_price: float = typer.Option(..., "--output", help="Price per million output tokens in USD."),
    cached_input_price: float = typer.Option(0.0, "--cached", help="Price per million cached input tokens in USD."),
):
    """Create or update a model pricing snapshot in the database."""
    console = Console()
    async def run():
        async with UnitOfWork() as uow:
            snapshot = await uow.model_calls.update_pricing_snapshot(
                pricing_source_id=source_id,
                model_name=model,
                input_price_per_million=input_price,
                output_price_per_million=output_price,
                cached_input_price_per_million=cached_input_price,
            )
            console.print(f"[bold green]Successfully updated model pricing snapshot #{snapshot.id} for {snapshot.model_name}.[/bold green]")
    asyncio.run(run())


@costs_app.command("report")
def cost_report_cmd(
    run_id: int = typer.Option(None, "--run-id", help="Filter report by a specific Run ID.")
):
    """Display actual vs hypothetical pricing report for the project workspace."""
    console = Console()
    
    async def run():
        async with UnitOfWork() as uow:
            # Get latest run if not provided
            active_run_id = run_id
            if active_run_id is None:
                db_runs = await uow.session.execute(
                    text("SELECT id FROM runs ORDER BY id DESC LIMIT 1")
                )
                row = db_runs.fetchone()
                if row:
                    active_run_id = row[0]
                else:
                    console.print("[yellow]No runs found in the database. Run scheduler first.[/yellow]")
                    return
            
            # Fetch project ID from database (always assume project 1 for local workspace)
            project_id = 1
            metrics = await uow.cost_benchmark.calculate_benchmarks(project_id, active_run_id)
            
            console.print(f"\n[bold green]=== LocalForge Cost Report (Run ID: {active_run_id}) ===[/bold green]\n")
            
            table = Table(title="Hybrid actual spend vs Competitor API-only baselines")
            table.add_column("Metric", style="cyan")
            table.add_column("LocalForge Actual", style="green")
            table.add_column("OpenAI API-Only", style="red")
            table.add_column("Anthropic API-Only", style="red")
            table.add_column("Google API-Only", style="red")
            
            table.add_row(
                "Total USD",
                f"${metrics['actual_paid_usd']:.4f}",
                f"${metrics['openai_hypothetical_usd']:.4f}",
                f"${metrics['anthropic_hypothetical_usd']:.4f}",
                f"${metrics['google_hypothetical_usd']:.4f}"
            )
            
            table.add_row(
                "Paid API Calls",
                str(metrics["actual_calls"]),
                "-",
                "-",
                "-"
            )
            
            table.add_row(
                "Local Calls Saved",
                str(metrics["local_calls_avoided"]),
                "-",
                "-",
                "-"
            )
            
            table.add_row(
                "Savings Amount",
                "-",
                f"${metrics['openai_savings_usd']:.4f}",
                f"${metrics['anthropic_savings_usd']:.4f}",
                f"${metrics['google_savings_usd']:.4f}"
            )
            
            console.print(table)
            console.print("\n*Note: Competitor baseline models are simulated token-cost calculations, not actual invoices.*")

    asyncio.run(run())


@costs_app.command("simulate")
def cost_simulate_cmd(
    run_id: int = typer.Option(None, "--run-id", help="Filter simulation by a specific Run ID.")
):
    """Estimate what the run would have cost if all model calls used API baselines."""
    console = Console()
    
    async def run():
        async with UnitOfWork() as uow:
            active_run_id = run_id
            if active_run_id is None:
                db_runs = await uow.session.execute(
                    text("SELECT id FROM runs ORDER BY id DESC LIMIT 1")
                )
                row = db_runs.fetchone()
                if row:
                    active_run_id = row[0]
                else:
                    console.print("[yellow]No runs found in the database.[/yellow]")
                    return
            
            project_id = 1
            sim = await uow.simulation.simulate_api_only_costs(project_id, active_run_id)
            
            console.print(f"\n[bold green]=== API-Only Cost Simulation Report (Run ID: {active_run_id}) ===[/bold green]\n")
            
            table = Table(title="Simulated 100% API execution vs LocalForge actual spend")
            table.add_column("Provider Profile", style="cyan")
            table.add_column("Simulated Cost (USD)", justify="right", style="red")
            table.add_column("Actual Paid (USD)", justify="right", style="green")
            table.add_column("Net Savings (USD)", justify="right", style="blue")
            
            table.add_row(
                "OpenAI Profile",
                f"${sim['openai_simulated_usd']:.4f}",
                f"${sim['actual_paid_usd']:.4f}",
                f"${sim['openai_savings_usd']:.4f}"
            )
            
            table.add_row(
                "Anthropic Profile",
                f"${sim['anthropic_simulated_usd']:.4f}",
                f"${sim['actual_paid_usd']:.4f}",
                f"${sim['anthropic_savings_usd']:.4f}"
            )
            
            table.add_row(
                "Google Profile",
                f"${sim['google_simulated_usd']:.4f}",
                f"${sim['actual_paid_usd']:.4f}",
                f"${sim['google_savings_usd']:.4f}"
            )
            
            console.print(table)
            console.print(f"\n[bold]Total calls simulated: {sim['total_calls']}[/bold]")
            console.print("*Note: Simulated values represent hypothetical 100% API execution based on pricing snapshots.*")

    asyncio.run(run())
