import asyncio
import logging
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from localforge.storage import UnitOfWork, db_manager

console = Console()
worktree_app = typer.Typer(help="Manage and inspect Worktree Attempt Manifests and PathLeases.")


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@worktree_app.command("leases")
def list_leases(project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID")) -> None:
    """List all active unexpired PathLeases for a project."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.path_leases is not None
            leases = await uow.path_leases.list_active_leases(project_id)

            if not leases:
                console.print(f"[yellow]No active leases found for project {project_id}[/yellow]")
                return

            table = Table(title=f"Active PathLeases (Project {project_id})")
            table.add_column("ID", justify="right")
            table.add_column("Owner ID", style="cyan")
            table.add_column("Target Path", style="yellow")
            table.add_column("TaskRun ID", justify="right")
            table.add_column("Expires At", style="magenta")

            for l in leases:
                table.add_row(
                    str(l.id),
                    l.owner_id,
                    l.target_path,
                    str(l.task_run_id),
                    l.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                )

            console.print(table)

    _run_async(_impl())


@worktree_app.command("reconcile")
def reconcile_worktrees(project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID")) -> None:
    """Run a report-only reconciliation of worktree manifests against physical filesystems."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.worktrees is not None
            res = await uow.worktrees.reconcile_worktree_manifests(project_id)

            console.print(f"[bold green]Worktree Reconciliation Summary (Project {project_id})[/bold green]")
            console.print(f"Total Manifests: {res['total_manifests']}")
            console.print(f"Active Worktrees: {res['active_worktrees']}")
            console.print(f"Reconciled Stale: {res['reconciled_stale']}")
            if res['stale_paths']:
                console.print("[yellow]Stale Worktree Paths:[/yellow]")
                for p in res['stale_paths']:
                    console.print(f"  - {p}")

    _run_async(_impl())
