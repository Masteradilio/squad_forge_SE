import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional


import typer
from rich.console import Console
from rich.table import Table

from localforge.models import domain
from localforge.models.enums import AutonomyLevel, ExecutionStrategy, LoopStatus, TriggerKind
from localforge.storage import UnitOfWork, db_manager

console = Console()
loops_app = typer.Typer(help="Manage and inspect Loop Control Plane definitions and runs.")


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@loops_app.command("list")
def list_loops(project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID")) -> None:
    """List all loop definitions for a project."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loops is not None
            loops = await uow.loops.list_loops_for_project(project_id)

            if not loops:
                console.print(f"[yellow]No loop definitions found for project {project_id}[/yellow]")
                return

            table = Table(title=f"Loop Definitions (Project {project_id})")
            table.add_column("ID", justify="right")
            table.add_column("Name", style="cyan")
            table.add_column("Enabled", style="green")
            table.add_column("Status", style="magenta")
            table.add_column("Trigger", style="yellow")
            table.add_column("Autonomy", style="blue")
            table.add_column("Max Budget USD", justify="right")

            for l in loops:
                table.add_row(
                    str(l.id),
                    l.name,
                    "Yes" if l.enabled else "No",
                    l.status.value,
                    l.trigger.kind.value,
                    l.autonomy.value,
                    f"${l.max_budget_usd:.2f}",
                )

            console.print(table)

    _run_async(_impl())


@loops_app.command("create")
def create_loop(
    project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID"),
    name: str = typer.Option(..., "--name", "-n", help="Loop name"),
    repository_path: str = typer.Option(".", "--repository-path", "-r", help="Repository path"),
    trigger_kind: str = typer.Option("MANUAL", "--trigger-kind", "-t", help="MANUAL, INTERVAL, CRON, or EVENT"),
    schedule: Optional[str] = typer.Option(None, "--schedule", help="Schedule string e.g. '5m'"),
    autonomy: str = typer.Option("L1_INSPECT", "--autonomy", "-a", help="L0_SIMULATE, L1_INSPECT, L2_ISOLATED, L3_UNATTENDED"),
    max_budget: float = typer.Option(5.0, "--max-budget", help="Maximum budget in USD"),
) -> None:
    """Create a new Loop Definition."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            assert uow.loops is not None

            proj = await uow.projects.get_project(project_id)
            if not proj:
                console.print(f"[bold red]Project {project_id} not found[/bold red]")
                raise typer.Exit(1)

            trigger = domain.LoopTrigger(
                kind=TriggerKind(trigger_kind.upper()),
                schedule=schedule,
            )

            loop_def = domain.LoopDefinition(
                project_id=project_id,
                name=name,
                repository_path=repository_path,
                enabled=True,
                trigger=trigger,
                autonomy=AutonomyLevel(autonomy.upper()),
                max_budget_usd=max_budget,
            )

            created = await uow.loops.create_loop(loop_def)
            console.print(f"[bold green]Loop '{created.name}' created with ID {created.id}[/bold green]")

    _run_async(_impl())


@loops_app.command("inspect")
def inspect_loop(loop_id: int = typer.Argument(..., help="Loop ID")) -> None:
    """Inspect details of a Loop Definition."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loops is not None
            loop_def = await uow.loops.get_loop(loop_id)
            if not loop_def:
                console.print(f"[bold red]Loop {loop_id} not found[/bold red]")
                raise typer.Exit(1)

            snapshot = await uow.loops.get_latest_snapshot(loop_id)

            console.print(f"[bold cyan]Loop Definition #{loop_def.id}: {loop_def.name}[/bold cyan]")
            console.print(f"Project ID: {loop_def.project_id}")
            console.print(f"Status: {loop_def.status.value}")
            console.print(f"Enabled: {loop_def.enabled}")
            console.print(f"Trigger Kind: {loop_def.trigger.kind.value} (Schedule: {loop_def.trigger.schedule})")
            console.print(f"Autonomy Level: {loop_def.autonomy.value}")
            console.print(f"Max Budget: ${loop_def.max_budget_usd:.2f}")

            if snapshot:
                console.print("\n[bold yellow]State Snapshot:[/bold yellow]")
                console.print(f"Total Runs: {snapshot.total_runs}")
                console.print(f"Total Cost USD: ${snapshot.total_cost_usd:.4f}")
                console.print(f"Circuit Status: {snapshot.circuit_status}")
                console.print(f"Active Run ID: {snapshot.active_run_id}")

    _run_async(_impl())


@loops_app.command("enable")
def enable_loop(loop_id: int = typer.Argument(..., help="Loop ID")) -> None:
    """Enable a Loop."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loops is not None
            res = await uow.loops.update_loop_status(loop_id, status=LoopStatus.IDLE, enabled=True)
            if not res:
                console.print(f"[bold red]Loop {loop_id} not found[/bold red]")
                raise typer.Exit(1)
            console.print(f"[bold green]Loop {loop_id} enabled[/bold green]")

    _run_async(_impl())


@loops_app.command("disable")
def disable_loop(loop_id: int = typer.Argument(..., help="Loop ID")) -> None:
    """Disable a Loop."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loops is not None
            res = await uow.loops.update_loop_status(loop_id, status=LoopStatus.DISABLED, enabled=False)

            if not res:
                console.print(f"[bold red]Loop {loop_id} not found[/bold red]")
                raise typer.Exit(1)
            console.print(f"[yellow]Loop {loop_id} disabled[/yellow]")

    _run_async(_impl())


@loops_app.command("pause")
def pause_loop(loop_id: int = typer.Argument(..., help="Loop ID")) -> None:
    """Pause an active Loop."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loop_coordinator is not None
            try:
                res = await uow.loop_coordinator.pause_loop(loop_id)
                console.print(f"[bold yellow]Loop {loop_id} paused[/bold yellow]")
            except ValueError as e:
                console.print(f"[bold red]{e}[/bold red]")
                raise typer.Exit(1)

    _run_async(_impl())


@loops_app.command("resume")
def resume_loop(loop_id: int = typer.Argument(..., help="Loop ID")) -> None:
    """Resume a paused Loop."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loop_coordinator is not None
            try:
                res = await uow.loop_coordinator.resume_loop(loop_id)
                console.print(f"[bold green]Loop {loop_id} resumed[/bold green]")
            except ValueError as e:
                console.print(f"[bold red]{e}[/bold red]")
                raise typer.Exit(1)

    _run_async(_impl())


@loops_app.command("run-now")
def run_now(
    loop_id: int = typer.Argument(..., help="Loop ID"),
    idempotency_key: Optional[str] = typer.Option(None, "--idempotency-key", "-k", help="Custom idempotency key"),
) -> None:
    """Trigger immediate execution of a Loop."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loop_coordinator is not None
            try:
                run = await uow.loop_coordinator.trigger_loop(
                    loop_id=loop_id,
                    trigger_kind=TriggerKind.MANUAL,
                    idempotency_key=idempotency_key,
                )
                console.print(f"[bold green]Loop run #{run.id} created with status {run.status.value} (Verdict: {run.triage_verdict.value})[/bold green]")
            except ValueError as e:
                console.print(f"[bold red]{e}[/bold red]")
                raise typer.Exit(1)

    _run_async(_impl())


@loops_app.command("history")
def loop_history(
    loop_id: int = typer.Argument(..., help="Loop ID"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of records"),
) -> None:
    """Display execution history for a Loop."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.loops is not None
            runs = await uow.loops.list_runs_for_loop(loop_id, limit=limit)

            if not runs:
                console.print(f"[yellow]No run history found for loop {loop_id}[/yellow]")
                return

            table = Table(title=f"Loop Execution History (Loop #{loop_id})")
            table.add_column("Run ID", justify="right")
            table.add_column("Status", style="magenta")
            table.add_column("Trigger", style="yellow")
            table.add_column("Verdict", style="cyan")
            table.add_column("Scheduler Run ID", justify="right")
            table.add_column("Items", justify="right")
            table.add_column("Cost USD", justify="right")
            table.add_column("Started At")

            for r in runs:
                table.add_row(
                    str(r.id),
                    r.status.value,
                    r.trigger_kind.value,
                    r.triage_verdict.value,
                    str(r.scheduler_run_id) if r.scheduler_run_id else "-",
                    str(r.items_processed),
                    f"${r.cost_usd:.4f}",
                    r.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                )

            console.print(table)

    _run_async(_impl())
