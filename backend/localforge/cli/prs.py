import asyncio
import os

import typer
from localforge.models.enums import ArtifactType, TaskStatus
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()


async def run_prs() -> None:
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
        assert uow.audits is not None

        project = await uow.projects.get_project_by_path(cwd)
        if not project:
            console.print(
                "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
            )
            raise typer.Exit(code=1)

        assert project.id is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)
        pr_ready_tasks = [
            t for t in tasks if t.status in (TaskStatus.PR_READY, TaskStatus.DONE)
        ]

        if not pr_ready_tasks:
            console.print(
                "[yellow]No Pull Requests found. "
                "Run 'localforge run' on ready tasks first.[/yellow]"
            )
            return

        table = Table(
            title="LocalForge OS — Propostas de Pull Requests Locais",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Task Key", style="green")
        table.add_column("Title", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("PR Description / md Artifact", style="magenta")

        pr_task_ids = [task.id for task in pr_ready_tasks if task.id is not None]
        runs_by_task = await uow.tasks.list_runs_for_tasks(pr_task_ids)
        latest_run_ids = [
            runs[0].id
            for runs in runs_by_task.values()
            if runs and runs[0].id is not None
        ]
        artifacts_by_run = await uow.audits.list_artifacts_for_task_runs(latest_run_ids)

        for t in pr_ready_tasks:
            assert t.id is not None
            pr_path = "pr.md (local artifact)"
            runs = runs_by_task.get(t.id, [])
            if runs:
                last_run = runs[0]
                assert last_run.id is not None
                artifacts = artifacts_by_run.get(last_run.id, [])
                pr_art = next((a for a in artifacts if a.type == ArtifactType.PR), None)
                if pr_art:
                    pr_path = pr_art.path

            table.add_row(t.key, t.title, t.status.value, pr_path)

        console.print(table)


def prs_cmd() -> None:
    """List generated local pull requests and their artifacts paths."""
    try:
        asyncio.run(run_prs())
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Command failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e
