import asyncio
from typing import Any

import typer
from localforge.models import domain
from localforge.models.enums import GraphMutationType
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
graph_app = typer.Typer(help="Manage server-owned dynamic task graphs and Deep Swarm.")


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@graph_app.command("init")
def init_graph(
    plan_id: int = typer.Option(..., "--plan-id", "-p"),
) -> None:
    """Create the initial (version 0) graph snapshot for a plan (V6-900)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            try:
                gv = await uow.task_graph.create_initial_graph_version(plan_id)
                console.print(
                    "[green]Graph initialised — "
                    f"plan_id={plan_id} version={gv.version} "
                    f"hash={gv.content_hash[:12]}...[/green]"
                )
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@graph_app.command("latest")
def latest_graph(plan_id: int = typer.Option(..., "--plan-id", "-p")) -> None:
    """Show the latest graph version snapshot for a plan."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            gv = await uow.task_graph.get_latest_graph_version(plan_id)
            if not gv:
                console.print(f"[yellow]No graph version found for plan {plan_id}.[/yellow]")
                return
            console.print(
                f"\n[bold]Plan {plan_id}[/bold] — "
                f"version=[cyan]{gv.version}[/cyan] "
                f"hash={gv.content_hash[:12]}..."
            )
            console.print(
                f"  Nodes: {len(gv.nodes_snapshot_json)} | Edges: {len(gv.edges_snapshot_json)}"
            )

    _run_async(_impl())


@graph_app.command("journal")
def show_journal(plan_id: int = typer.Option(..., "--plan-id", "-p")) -> None:
    """Show the full append-only mutation journal for a plan."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            journal = await uow.task_graph.get_mutation_journal(plan_id)
            if not journal:
                console.print(f"[yellow]No mutations found for plan {plan_id}.[/yellow]")
                return
            table = Table(title=f"Mutation Journal — plan {plan_id}")
            table.add_column("Ver")
            table.add_column("Type")
            table.add_column("Actor")
            table.add_column("Reason")
            table.add_column("Hash")
            for m in journal:
                table.add_row(
                    str(m.graph_version),
                    str(m.mutation_type),
                    m.actor_agent_id,
                    m.reason[:50],
                    m.content_hash[:12],
                )
            console.print(table)

    _run_async(_impl())


@graph_app.command("mutate")
def mutate(
    plan_id: int = typer.Option(..., "--plan-id", "-p"),
    mutation_type: str = typer.Option(..., "--type", "-t"),
    actor: str = typer.Option(..., "--actor", "-a"),
    reason: str = typer.Option(..., "--reason", "-r"),
    run_id: int = typer.Option(..., "--run-id"),
    expected_version: int = typer.Option(..., "--expected-version", "-e"),
    payload_json: str = typer.Option("{}", "--payload"),
) -> None:
    """Apply a validated mutation to the task graph (V6-901)."""
    import json as _json

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            try:
                mut_type = GraphMutationType(mutation_type)
                payload = _json.loads(payload_json)
                mutation, new_gv = await uow.task_graph.apply_mutation(
                    plan_id=plan_id,
                    mutation_type=mut_type,
                    actor_agent_id=actor,
                    reason=reason,
                    payload=payload,
                    expected_graph_version=expected_version,
                    deep_swarm_run_id=run_id,
                )
                console.print(
                    "[green]Mutation applied — "
                    f"version={new_gv.version} "
                    f"hash={new_gv.content_hash[:12]}...[/green]"
                )
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@graph_app.command("reconcile")
def reconcile(plan_id: int = typer.Option(..., "--plan-id", "-p")) -> None:
    """Restore graph, ready queue, leases, attempts, and artifacts after a crash."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            try:
                report = await uow.task_graph.reconcile_after_restart(plan_id)
                console.print(
                    "[cyan]Reconciliation — "
                    f"status={report['status']} "
                    f"reset={report['reconciled_nodes']}[/cyan]"
                )
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@graph_app.command("deep-create")
def deep_create(
    plan_id: int = typer.Option(..., "--plan-id", "-p"),
    enabled: bool = typer.Option(
        False, "--enabled/--disabled", help="Opt-in to Deep Swarm (V6-903)"
    ),
    prefer_light: bool = typer.Option(
        True,
        "--prefer-light/--force-deep",
        help="Fallback to Light Swarm when eligible",
    ),
) -> None:
    """Create a Deep Swarm run for a plan (disabled by default)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            policy = domain.DeepSwarmPolicy(enabled=enabled, prefer_light_swarm=prefer_light)
            try:
                run = await uow.task_graph.create_deep_swarm_run(plan_id, policy)
                console.print(
                    f"[{'green' if enabled else 'yellow'}]"
                    f"Deep Swarm created — run_id={run.id} "
                    f"status={run.status}[/]"
                )
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@graph_app.command("deep-enable")
def deep_enable(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Opt-in to Deep Swarm execution (V6-903)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            try:
                run = await uow.task_graph.enable_deep_swarm(run_id)
                console.print(
                    f"[green]Deep Swarm enabled — run_id={run_id} status={run.status}[/green]"
                )
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())


@graph_app.command("deep-kill")
def deep_kill(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Kill a Deep Swarm run (V6-904)."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.task_graph is not None
            try:
                run = await uow.task_graph.kill_deep_swarm(run_id)
                console.print(
                    f"[red]Deep Swarm killed — run_id={run_id} verdict={run.verdict}[/red]"
                )
            except ValueError as e:
                console.print(f"[red]{e}[/red]")

    _run_async(_impl())
