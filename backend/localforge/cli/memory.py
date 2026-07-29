import asyncio
from typing import Any

import typer
from localforge.models import domain
from localforge.models.enums import (
    MemoryFactCategory,
    MemoryRelationType,
    MemoryValidityStatus,
)
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
memory_app = typer.Typer(help="Manage provenance-aware operational memory, relations, consolidation, and retrieval.")


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@memory_app.command("list")
def list_facts(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    category: str | None = typer.Option(None, "--category", "-c"),
    validity: str | None = typer.Option(None, "--validity", "-v"),
) -> None:
    """List operational memory facts for a project."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.memory is not None
            cat_enum = MemoryFactCategory(category) if category else None
            val_enum = MemoryValidityStatus(validity) if validity else None
            facts = await uow.memory.list_facts(project_id, category=cat_enum, validity=val_enum)

            if not facts:
                console.print(f"[yellow]No memory facts found for project {project_id}.[/yellow]")
                return

            table = Table(title=f"Memory Facts — Project {project_id}")
            table.add_column("ID")
            table.add_column("Category")
            table.add_column("Fact")
            table.add_column("Validity")
            table.add_column("Conf")
            table.add_column("Task")
            table.add_column("Pinned")

            for f in facts:
                table.add_row(
                    str(f.id),
                    f.category.value,
                    f.fact[:60],
                    f.validity.value,
                    f"{f.confidence:.2f}",
                    f.task_key or "-",
                    "Yes" if f.pinned else "No",
                )
            console.print(table)

    _run_async(_impl())


@memory_app.command("add")
def add_fact(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    fact_text: str = typer.Option(..., "--fact", "-f"),
    category: str = typer.Option("OBSERVED_FACT", "--category", "-c"),
    task_key: str | None = typer.Option(None, "--task-key", "-t"),
    verifier: str | None = typer.Option(None, "--verifier"),
    pinned: bool = typer.Option(False, "--pinned"),
) -> None:
    """Add a new provenance-aware memory fact."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.memory is not None
            fact = domain.MemoryFact(
                project_id=project_id,
                fact=fact_text,
                category=MemoryFactCategory(category),
                task_key=task_key,
                verifier=verifier,
                pinned=pinned,
                source="cli",
            )
            created = await uow.memory.create_fact(fact)
            console.print(f"[green]Memory fact created — ID={created.id} category={created.category.value}[/green]")

    _run_async(_impl())


@memory_app.command("relate")
def relate_facts(
    source_id: int = typer.Option(..., "--source", "-s"),
    target_id: int = typer.Option(..., "--target", "-t"),
    relation_type: str = typer.Option("SUPERSEDES", "--type", "-r"),
    reason: str = typer.Option("Manual relation", "--reason"),
) -> None:
    """Create a relationship between memory facts (V6-1001)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.memory is not None
            try:
                rel = await uow.memory.add_relation(
                    source_fact_id=source_id,
                    target_fact_id=target_id,
                    relation_type=MemoryRelationType(relation_type),
                    provenance={"reason": reason, "actor": "cli"},
                )
                console.print(f"[green]Relation created — ID={rel.id} type={rel.relation_type.value}[/green]")
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@memory_app.command("consolidate")
def consolidate(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    max_age_days: int = typer.Option(90, "--max-age-days"),
) -> None:
    """Run background memory consolidation (V6-1002)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.memory is not None
            policy = domain.MemoryRetentionPolicy(max_fact_age_days=max_age_days)
            res = await uow.memory.consolidate_memory(project_id, policy)
            console.print(
                "[cyan]Consolidation complete - "
                f"Expired: {res['expired_count']} | "
                f"Duplicates: {res['duplicate_count']} | "
                f"Active: {res['remaining_active_facts']}[/cyan]"
            )

    _run_async(_impl())


@memory_app.command("retrieve")
def retrieve(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    query: str = typer.Option(..., "--query", "-q"),
    task_key: str | None = typer.Option(None, "--task-key", "-t"),
    limit: int = typer.Option(5, "--limit", "-l"),
) -> None:
    """Perform structured and lexical retrieval (V6-1003)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.memory is not None
            flt = domain.MemoryRetrievalFilter(task_key=task_key) if task_key else None
            facts = await uow.memory.retrieve_advanced(project_id, query=query, filters=flt, limit=limit)

            console.print(f"\n[bold]Retrieved Facts ({len(facts)}):[/bold]")
            for f in facts:
                console.print(f"  • [{f.category.value}] {f.fact} [validity={f.validity.value}]")

    _run_async(_impl())


@memory_app.command("inject")
def inject_context(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    task_key: str = typer.Option(..., "--task-key", "-t"),
) -> None:
    """Render safe read-only memory context for prompt injection (V6-1004)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.memory is not None
            prompt = await uow.memory.inject_scoped_memory(project_id, task_key)
            console.print(prompt)

    _run_async(_impl())
