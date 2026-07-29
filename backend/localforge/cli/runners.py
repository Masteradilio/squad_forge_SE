import asyncio
from typing import Any

import typer
from localforge.models import domain
from localforge.models.enums import RunnerHealthState, RunnerLane
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
runners_app = typer.Typer(
    help="Manage and inspect RunnerPool states, capabilities, health, and dispatch."
)


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@runners_app.command("list")
def list_runners() -> None:
    """List all registered runners and their current states."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.runner_pool is not None
            runners = await uow.runner_pool.list_runners()

            if not runners:
                console.print("[yellow]No runners registered in the pool.[/yellow]")
                return

            table = Table(title="RunnerPool State Overview")
            table.add_column("Runner ID", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("Lane", style="magenta")
            table.add_column("Health", style="bold green")
            table.add_column("Active/Max Capacity", justify="right")
            table.add_column("Success Rate", justify="right")

            for r in runners:
                health_style = (
                    "green"
                    if r.health_state == RunnerHealthState.READY
                    else "yellow"
                    if r.health_state == RunnerHealthState.DEGRADED
                    else "red"
                )
                table.add_row(
                    r.runner_id,
                    r.name,
                    r.lane.value,
                    f"[{health_style}]{r.health_state.value}[/{health_style}]",
                    f"{r.active_tasks_count}/{r.max_concurrency}",
                    f"{r.success_rate * 100:.1f}%",
                )

            console.print(table)

    _run_async(_impl())


@runners_app.command("register")
def register_runner(
    runner_id: str = typer.Option(..., "--id", "-i", help="Runner ID"),
    name: str = typer.Option(..., "--name", "-n", help="Runner Name"),
    lane: str = typer.Option(
        "INLINE", "--lane", "-l", help="Lane (INLINE, BACKGROUND, SANDBOX, ISOLATED)"
    ),
    max_concurrency: int = typer.Option(4, "--max-concurrency", "-c", help="Max Concurrency"),
) -> None:
    """Register a new runner in the pool."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.runner_pool is not None
            lane_enum = RunnerLane(lane)
            caps = domain.RunnerCapability(lane=lane_enum, max_concurrency=max_concurrency)
            res = await uow.runner_pool.register_runner(
                runner_id=runner_id,
                name=name,
                lane=lane_enum,
                capabilities=caps,
                max_concurrency=max_concurrency,
            )
            console.print(
                f"[bold green]Runner '{res.runner_id}' registered successfully.[/bold green]"
            )

    _run_async(_impl())


@runners_app.command("health")
def update_health(
    runner_id: str = typer.Option(..., "--id", "-i", help="Runner ID"),
    health: str = typer.Option(
        ...,
        "--health",
        "-h",
        help="Health State (READY, BUSY, DEGRADED, UNAVAILABLE, DRAINING, QUARANTINED)",
    ),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Quarantine Reason"),
) -> None:
    """Update health state of a runner."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.runner_pool is not None
            res = await uow.runner_pool.update_runner_health(
                runner_id=runner_id,
                health_state=RunnerHealthState(health),
                quarantine_reason=reason,
            )
            console.print(
                f"[bold green]Runner '{res.runner_id}' health updated to '{res.health_state.value}'.[/bold green]"
            )

    _run_async(_impl())
