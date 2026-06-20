import asyncio
import json
import os
import sys
from pathlib import Path

import typer
from localforge.prd.compiler import import_prd
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console

console = Console()
PRD_PATH_ARG = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True)
DRY_RUN_OPT = typer.Option(False, "--dry-run", help="Preview epics/tasks without persisting.")
JSON_OUTPUT_OPT = typer.Option(
    False, "--json", help="Output import result in machine-readable JSON format."
)


async def run_import_prd(path: Path, dry_run: bool, json_output: bool) -> None:
    cwd = os.getcwd()
    if not path.exists():
        raise ValueError(f"PRD file not found: {path}")

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.get_project_by_path(cwd)
        if not project or project.id is None:
            raise ValueError("Workspace not initialized. Run 'localforge init' first.")
        project_id = project.id

    result = await import_prd(path, project_id, db_manager=db_manager, dry_run=dry_run)

    payload = result.model_dump()
    if json_output:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        sys.stdout.flush()
        return

    mode = "dry-run" if dry_run else "import"
    console.print(f"[bold green]PRD {mode} complete[/bold green]")
    console.print(f"  Document hash: {result.document_hash}")
    console.print(f"  Changed: {result.changed}")
    console.print(f"  Epics: {result.epics_created}")
    console.print(f"  Tasks: {result.tasks_created}")


def import_prd_cmd(
    path: Path = PRD_PATH_ARG,
    dry_run: bool = DRY_RUN_OPT,
    json_output: bool = JSON_OUTPUT_OPT,
) -> None:
    try:
        asyncio.run(run_import_prd(path, dry_run, json_output))
    except Exception as e:
        console.print(f"[bold red]PRD import failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e
