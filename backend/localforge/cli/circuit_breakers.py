import asyncio
from typing import Any

import typer
from localforge.models.enums import CircuitScope
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
breakers_app = typer.Typer(help="Manage and inspect Circuit Breakers.")


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@breakers_app.command("list")
def list_breakers(
    project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID"),
) -> None:
    """List all circuit breakers for a project."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.circuit_breakers is not None
            breakers = await uow.circuit_breakers.list_breakers_for_project(project_id)

            if not breakers:
                console.print(
                    f"[yellow]No circuit breakers found for project {project_id}[/yellow]"
                )
                return

            table = Table(title=f"Circuit Breakers (Project {project_id})")
            table.add_column("ID", justify="right")
            table.add_column("Scope", style="cyan")
            table.add_column("Target ID", style="yellow")
            table.add_column("State", style="magenta")
            table.add_column("Failures", justify="right")
            table.add_column("Stagnation", justify="right")
            table.add_column("Reason", style="red")

            for b in breakers:
                table.add_row(
                    str(b.id),
                    b.scope.value,
                    b.target_id,
                    b.state.value,
                    str(b.consecutive_failures),
                    str(b.stagnation_count),
                    b.reason or "-",
                )

            console.print(table)

    _run_async(_impl())


@breakers_app.command("reset")
def reset_breaker(
    project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID"),
    scope: str = typer.Option(
        ..., "--scope", "-s", help="Scope e.g. LOOP, RUN, ITEM, TASK, PROVIDER"
    ),
    target_id: str = typer.Option(..., "--target-id", "-t", help="Target ID"),
    reason: str = typer.Option("Manual reset via CLI", "--reason", "-r", help="Reason for reset"),
) -> None:
    """Manually reset a circuit breaker to CLOSED state."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.circuit_breakers is not None
            try:
                scope_enum = CircuitScope(scope.upper())
            except ValueError as exc:
                console.print(f"[bold red]Invalid scope: {scope}[/bold red]")
                raise typer.Exit(1) from exc

            res = await uow.circuit_breakers.reset_breaker(
                project_id=project_id,
                scope=scope_enum,
                target_id=target_id,
                actor_id="cli_user",
                reason=reason,
            )
            console.print(
                f"[bold green]Circuit breaker {res.scope.value}:{res.target_id} reset to CLOSED[/bold green]"
            )

    _run_async(_impl())
