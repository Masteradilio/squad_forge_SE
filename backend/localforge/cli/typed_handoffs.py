import asyncio
from typing import Any

import typer
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
handoffs_app = typer.Typer(
    help="Manage, inspect, and verify Typed Handoff Artifacts and evidence lineage."
)


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@handoffs_app.command("list")
def list_artifacts(
    task_run_id: int = typer.Option(..., "--task-run-id", "-t", help="TaskRun ID"),
) -> None:
    """List typed handoff artifacts produced during a task run."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.typed_handoffs is not None
            artifacts = await uow.typed_handoffs.list_artifacts_for_run(task_run_id)

            if not artifacts:
                console.print(
                    f"[yellow]No typed handoff artifacts found for TaskRun {task_run_id}[/yellow]"
                )
                return

            table = Table(title=f"Typed Handoff Artifacts (TaskRun {task_run_id})")
            table.add_column("ID", justify="right")
            table.add_column("Type", style="magenta")
            table.add_column("Producer", style="cyan")
            table.add_column("Consumer", style="cyan")
            table.add_column("Content Hash (SHA-256)", style="yellow")
            table.add_column("Consumed", justify="center")

            for a in artifacts:
                table.add_row(
                    str(a.id),
                    a.artifact_type.value,
                    a.producer_agent_id,
                    a.consumer_agent_id,
                    f"{a.content_hash[:16]}...",
                    "[green]YES[/green]" if a.is_consumed else "[gray]NO[/gray]",
                )

            console.print(table)

    _run_async(_impl())


@handoffs_app.command("verify")
def verify_artifact(artifact_id: int = typer.Option(..., "--id", "-i", help="Artifact ID")) -> None:
    """Validate SHA-256 content_hash integrity of a stored handoff artifact."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.typed_handoffs is not None
            valid, msg = await uow.typed_handoffs.validate_artifact_integrity(artifact_id)

            if valid:
                console.print(
                    f"[bold green]Artifact ID {artifact_id} integrity VERIFIED (SHA-256 hash matches).[/bold green]"
                )
            else:
                console.print(f"[bold red]INTEGRITY VIOLATION: {msg}[/bold red]")

    _run_async(_impl())


@handoffs_app.command("render")
def render_artifact(artifact_id: int = typer.Option(..., "--id", "-i", help="Artifact ID")) -> None:
    """Render human-readable Markdown summary of a handoff artifact."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.typed_handoffs is not None
            await uow.typed_handoffs.list_artifacts_for_run(1)  # trigger query session
            # fetch specific artifact
            from localforge.storage.orm import TypedHandoffArtifactORM
            from sqlalchemy import select

            assert uow.session is not None
            res = await uow.session.execute(
                select(TypedHandoffArtifactORM).where(TypedHandoffArtifactORM.id == artifact_id)
            )

            orm_obj = res.scalar_one_or_none()
            if not orm_obj:
                console.print(f"[red]Artifact ID {artifact_id} not found.[/red]")
                return

            md = uow.typed_handoffs.render_markdown_summary(orm_obj.to_domain())
            console.print(md)

    _run_async(_impl())
