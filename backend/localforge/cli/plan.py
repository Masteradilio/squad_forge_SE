import asyncio
import os

import typer
from localforge.models.enums import TaskStatus
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()


async def run_plan(approve: str | None, approve_all: bool) -> None:
    cwd = os.getcwd()
    lf_dir = os.path.join(cwd, ".localforge")
    if not os.path.exists(lf_dir):
        console.print(
            "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
        )
        raise typer.Exit(code=1)

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None

        project = await uow.projects.get_project_by_path(cwd)
        if not project:
            console.print(
                "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
            )
            raise typer.Exit(code=1)

        assert project.id is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)

        if approve_all:
            approved_count = 0
            for task in tasks:
                if task.status in (TaskStatus.BACKLOG, TaskStatus.PLANNING):
                    assert task.id is not None
                    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
                    approved_count += 1
            assert uow.session is not None
            await uow.session.commit()
            console.print(
                f"[green]Approved all planning/backlog tasks: "
                f"{approved_count} tasks marked as READY.[/green]"
            )
            return

        if approve:
            target_task = None
            for t in tasks:
                if t.key == approve:
                    target_task = t
                    break
            if not target_task:
                console.print(f"[bold red]Task with key '{approve}' not found.[/bold red]")
                raise typer.Exit(code=1)

            if target_task.status not in (TaskStatus.BACKLOG, TaskStatus.PLANNING):
                console.print(
                    f"[yellow]Task {approve} is already in status: "
                    f"{target_task.status.value}[/yellow]"
                )
                return

            assert target_task.id is not None
            await uow.tasks.update_task_status(target_task.id, TaskStatus.READY)
            assert uow.session is not None
            await uow.session.commit()
            console.print(f"[green]Approved task {approve}: status changed to READY.[/green]")
            return

        # Listing pending plans
        planning_tasks = [t for t in tasks if t.status in (TaskStatus.BACKLOG, TaskStatus.PLANNING)]
        if not planning_tasks:
            console.print("[yellow]No tasks found in BACKLOG or PLANNING status.[/yellow]")
            return

        table = Table(
            title="LocalForge OS — Plan Pending Approval",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Task Key", style="green")
        table.add_column("Title", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Acceptance Criteria", style="magenta")

        for t in planning_tasks:
            ac_text = ", ".join(t.acceptance_criteria)
            table.add_row(t.key, t.title, t.status.value, ac_text)

        console.print(table)
        console.print("\nTo approve a task plan, run:")
        console.print("  [bold cyan]localforge plan --approve <task_key>[/bold cyan]")
        console.print("To approve all pending tasks in batch, run:")
        console.print("  [bold cyan]localforge plan --approve-all[/bold cyan]")


def plan_cmd(
    approve: str = typer.Option(
        None,
        "--approve",
        help="Approve a specific task plan by its key (e.g. LF-1001).",
    ),
    approve_all: bool = typer.Option(
        False,
        "--approve-all",
        help="Approve all tasks currently in planning/backlog.",
    ),
) -> None:
    """Manage backlog planning and approve task implementation plans."""
    try:
        asyncio.run(run_plan(approve, approve_all))
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Command failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e
