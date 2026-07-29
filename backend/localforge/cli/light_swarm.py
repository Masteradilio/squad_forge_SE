import asyncio
from typing import Any

import typer
from localforge.models import domain
from localforge.models.enums import SwarmNodeType, SwarmStrategy, TypedArtifactType
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
swarm_app = typer.Typer(help="Manage Light Swarm multi-agent plans, executions, and observability.")


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@swarm_app.command("start")
def start_swarm(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    task_run_id: int = typer.Option(..., "--task-run-id", "-t"),
    strategy: str = typer.Option("LIGHT", "--strategy", "-s"),
) -> None:
    """Start a minimal single-node Light Swarm (baseline/fallback)."""

    async def _impl() -> None:
        nodes = [
            domain.SwarmNode(
                node_id="node-0",
                node_type=SwarmNodeType.RESEARCH,
                title="Research",
                description="Initial research phase",
            ),
            domain.SwarmNode(
                node_id="node-1",
                node_type=SwarmNodeType.VERIFY,
                title="Verify",
                description="Verification phase",
                depends_on=["node-0"],
                required_input_artifact_type=TypedArtifactType.RESEARCH,
            ),
        ]
        edges: list[tuple[str, str]] = [("node-0", "node-1")]
        policy = domain.SwarmPolicy(
            strategy=SwarmStrategy(strategy), require_independent_checker=False
        )

        async with UnitOfWork(db_manager) as uow:
            assert uow.light_swarm is not None
            plan = await uow.light_swarm.create_plan(
                project_id=project_id,
                task_run_id=task_run_id,
                nodes=nodes,
                edges=edges,
                policy=policy,
                strategy=SwarmStrategy(strategy),
            )
            run = await uow.light_swarm.start_swarm(plan.id)  # type: ignore[arg-type]
            console.print(
                f"[green]Swarm started — plan_id={plan.id} run_id={run.id} status={run.status}[/green]"
            )

    _run_async(_impl())


@swarm_app.command("status")
def status_swarm(
    run_id: int = typer.Option(..., "--run-id", "-r", help="SwarmRun ID"),
) -> None:
    """Show the current DAG status of a swarm run."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.light_swarm is not None
            try:
                view = await uow.light_swarm.get_dag_view(run_id)
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
                return

            console.print(
                f"\n[bold]SwarmRun {run_id}[/bold] — status=[cyan]{view['status']}[/cyan] strategy={view['strategy']}"
            )
            console.print(
                f"  Cost: ${view['cumulative_cost_usd']:.4f} | Tokens: {view['cumulative_tokens']:,}"
            )
            console.print(f"  Active nodes: {view['active_node_ids']}")
            console.print(f"  Verdict: {view['verdict']}")

            table = Table(title="DAG Nodes")
            table.add_column("ID")
            table.add_column("Type")
            table.add_column("Title")
            table.add_column("Status")
            table.add_column("Depends On")

            for n in view["nodes"]:
                table.add_row(
                    n["node_id"],
                    n["node_type"],
                    n["title"],
                    str(n["status"]),
                    ", ".join(n["depends_on"]) or "-",
                )
            console.print(table)

    _run_async(_impl())


@swarm_app.command("pause")
def pause_swarm(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Pause a running swarm."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.light_swarm is not None
            try:
                run = await uow.light_swarm.pause_swarm(run_id)
                console.print(f"[yellow]SwarmRun {run_id} paused — status={run.status}[/yellow]")
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@swarm_app.command("kill")
def kill_swarm(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Kill a swarm at swarm scope, releasing all active nodes."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.light_swarm is not None
            try:
                run = await uow.light_swarm.kill_swarm(run_id)
                console.print(f"[red]SwarmRun {run_id} killed — verdict={run.verdict}[/red]")
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@swarm_app.command("summary")
def summary_swarm(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Export replayable SwarmExecutionSummary for a completed run."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.light_swarm is not None
            try:
                s = await uow.light_swarm.aggregate_result(run_id)
                console.print(f"\n[bold]SwarmExecutionSummary — run_id={run_id}[/bold]")
                console.print(f"  Strategy: {s.strategy}")
                console.print(f"  Verdict: {s.verdict}")
                console.print(f"  Cost: ${s.total_cost_usd:.4f}")
                console.print(f"  Tokens: {s.total_tokens:,}")
                console.print(f"  Duration: {s.duration_seconds:.1f}s")
                console.print(f"  Artifact IDs: {s.artifact_ids}")
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())
