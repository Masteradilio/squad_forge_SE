import asyncio
import json
import os
import sys
from typing import Any

import typer
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()


async def get_status_data() -> dict[str, Any]:
    """Retrieve summarized project status statistics from the database."""
    cwd = os.getcwd()
    lf_dir = os.path.join(cwd, ".localforge")

    if not os.path.exists(lf_dir):
        return {
            "initialized": False,
            "message": "Workspace not initialized. Run 'localforge init' first.",
        }

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.executions is not None

        # 1. Fetch Project
        project = await uow.projects.get_project_by_path(cwd)
        if not project:
            return {
                "initialized": False,
                "message": "Workspace not initialized. Run 'localforge init' first.",
            }

        # 2. Fetch Tasks and Epics
        assert project.id is not None
        tasks = await uow.tasks.list_tasks_for_project(project.id)
        epics = await uow.tasks.list_epics_for_project(project.id)

        # Summarize Task Counts by status
        status_counts: dict[str, int] = {}
        for task in tasks:
            status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1

        # 3. Fetch Runs
        runs = await uow.executions.list_runs_for_project(project.id)
        last_run = runs[0] if runs else None

        # 4. Fetch Agents
        agents = await uow.executions.list_active_agents()

        return {
            "initialized": True,
            "project": {
                "id": project.id,
                "name": project.name,
                "root_path": project.root_path,
                "default_branch": project.default_branch,
                "remote_url": project.remote_url,
            },
            "epics_count": len(epics),
            "tasks": {
                "total": len(tasks),
                "by_status": status_counts,
            },
            "last_run": {
                "id": last_run.id,
                "mode": last_run.mode.value,
                "status": last_run.status.value,
                "started_at": last_run.started_at.isoformat(),
                "initiated_by": last_run.initiated_by,
                "summary": last_run.summary,
            }
            if last_run
            else None,
            "active_agents": [
                {
                    "name": agent.name,
                    "role": agent.role.value,
                    "model_profile_id": agent.model_profile_id,
                }
                for agent in agents
            ],
        }


async def run_status(json_output: bool) -> None:
    """Execute status queries and format the outputs."""
    data = await get_status_data()

    if json_output:
        sys.stdout.write(json.dumps(data, indent=2))
        sys.stdout.flush()
        if not data.get("initialized", False):
            raise typer.Exit(code=1)
        return

    if not data.get("initialized", False):
        console.print(f"[bold red]✖ Error:[/bold red] {data['message']}")
        raise typer.Exit(code=1)

    proj = data["project"]
    console.print(f"[bold green]Workspace Status:[/bold green] {proj['name']}")
    console.print(f"  [bold]Path:[/bold] {proj['root_path']}")
    console.print(f"  [bold]Git Branch:[/bold] {proj['default_branch']}")
    if proj["remote_url"]:
        console.print(f"  [bold]Git Remote:[/bold] {proj['remote_url']}")

    # Epic and Task table
    task_info = data["tasks"]
    console.print(f"\n[bold magenta]Task Statistics ({task_info['total']} total):[/bold magenta]")
    if task_info["total"] > 0:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green")

        for status, count in task_info["by_status"].items():
            table.add_row(status, str(count))
        console.print(table)
    else:
        console.print("  No tasks found. Import a PRD to create tasks.")

    # Last Run Info
    run_info = data["last_run"]
    console.print("\n[bold magenta]Last Session Execution:[/bold magenta]")
    if run_info:
        console.print(f"  [bold]Run ID:[/bold] {run_info['id']}")
        console.print(f"  [bold]Mode:[/bold] {run_info['mode']}")
        status_color = "green" if run_info["status"] == "COMPLETED" else "yellow"
        console.print(
            f"  [bold]Status:[/bold] [{status_color}]{run_info['status']}[/{status_color}]"
        )
        console.print(f"  [bold]Started At:[/bold] {run_info['started_at']}")
        console.print(f"  [bold]Initiated By:[/bold] {run_info['initiated_by']}")
        if run_info["summary"]:
            console.print(f"  [bold]Summary:[/bold] {run_info['summary']}")
    else:
        console.print("  No runs recorded yet.")

    # Active Agents Info
    agents = data["active_agents"]
    console.print("\n[bold magenta]Active Agents registered:[/bold magenta]")
    if agents:
        agent_table = Table(show_header=True, header_style="bold cyan")
        agent_table.add_column("Agent Name", style="green")
        agent_table.add_column("Role", style="magenta")
        agent_table.add_column("Model Profile", style="yellow")
        for agent in agents:
            agent_table.add_row(agent["name"], agent["role"], agent["model_profile_id"])
        console.print(agent_table)
    else:
        console.print("  No active agents online.")


def status_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Output status summary in machine-readable JSON format."
    ),
) -> None:
    """Display project, task, and daemon status summary."""
    try:
        asyncio.run(run_status(json_output))
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Status execution failed with unexpected error:[/bold red] {e}")
        raise typer.Exit(code=1) from e
