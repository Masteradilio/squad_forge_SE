import asyncio
import os

import typer
from localforge.models import domain
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()
squad_app = typer.Typer(help="Manage squad configuration and routing.")


async def run_squad_composition() -> None:
    cwd = os.getcwd()
    lf_dir = os.path.join(cwd, ".localforge")
    if not os.path.exists(lf_dir):
        console.print(
            "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
        )
        raise typer.Exit(code=1)

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.routing is not None

        project = await uow.projects.get_project_by_path(cwd)
        if not project:
            console.print(
                "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
            )
            raise typer.Exit(code=1)

        assert project.id is not None

        table = Table(
            title=f"LocalForge OS — Squad Composition for Project: {project.name}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Squad Role", style="green", width=20)
        table.add_column("Seniority Class", style="yellow", width=20)
        table.add_column("Responsibility", style="white")
        table.add_column("Mapped Model", style="magenta")
        table.add_column("Provider", style="blue")

        for role, meta in domain.SQUAD_ROLE_METADATA.items():
            model_profile_id = None
            provider = "localforge"

            if meta.seniority_class == domain.SeniorityClass.HUMAN:
                model_profile_id = "Human"
                provider = "human"
            elif meta.seniority_class == domain.SeniorityClass.DETERMINISTIC_ONLY:
                model_profile_id = "Deterministic Gate"
                provider = "harness"
            else:
                route_val = await uow.routing.get_model_for_role(
                    project.id, meta.default_agent_role
                )
                if route_val:
                    model_profile_id = route_val
                    routes = await uow.routing.list_routes(project.id)
                    for r in routes:
                        if r.role == meta.default_agent_role:
                            provider = r.provider
                            break
                else:
                    if meta.seniority_class in (
                        domain.SeniorityClass.CHIEF_ONLY,
                        domain.SeniorityClass.CHIEF_LED,
                    ):
                        model_profile_id = "gpt-5.5-large"
                        provider = "openrouter"
                    elif meta.seniority_class == domain.SeniorityClass.LOCAL_ASSISTED:
                        model_profile_id = "granite4.1:8b"
                        provider = "ollama"
                    else:
                        model_profile_id = "local_small"
                        provider = "ollama"

            table.add_row(
                role.value,
                meta.seniority_class.value,
                meta.responsibility,
                model_profile_id or "",
                provider,
            )

        console.print(table)


@squad_app.command(
    name="composition", help="Show the current squad composition and routing model assignment."
)
def squad_composition_cmd() -> None:
    try:
        asyncio.run(run_squad_composition())
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Command failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e


async def run_orchestrate(prd_path: str) -> None:
    import os
    from pathlib import Path

    from localforge.cli.import_prd import run_import_prd
    from localforge.cli.plan import run_plan
    from localforge.cli.run import run_execution

    console.print(
        f"[bold green]Scrum Master Orchestrator Started[/bold green] parsing PRD: {prd_path}"
    )

    # 1. Parse PRD
    await run_import_prd(Path(prd_path), dry_run=False, json_output=False)

    # 2. Map Tasks
    # Implement deterministic mapping of tasks to roles based on complexity
    cwd = os.getcwd()
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.session is not None
        project = await uow.projects.get_project_by_path(cwd)
        assert project is not None
        assert project.id is not None

        tasks = await uow.tasks.list_tasks_for_project(project.id)
        for task in tasks:
            if task.status in (domain.TaskStatus.BACKLOG, domain.TaskStatus.PLANNING):
                title_desc = f"{task.title} {task.description}".lower()

                # Deterministic logic for mapping complexity
                if "frontend" in title_desc or "visualiza" in title_desc or "crud" in title_desc:
                    seniority = domain.SeniorityClass.CHIEF_ONLY.value
                    risk_level = "high"
                elif "testes" in title_desc or "valida" in title_desc:
                    seniority = domain.SeniorityClass.LOCAL_ASSISTED.value
                    risk_level = "low"
                else:
                    seniority = domain.SeniorityClass.CHIEF_LED.value
                    risk_level = "medium"

                task.risk_level = risk_level
                if "task_contract" not in task.metadata:
                    task.metadata["task_contract"] = {}
                task.metadata["task_contract"]["seniority_class"] = seniority

                await uow.tasks.update_task(task)

        await uow.session.commit()
    console.print("[bold green]Tasks mapped to roles based on complexity.[/bold green]")

    # 3. Plan / Approve all
    await run_plan(approve=None, approve_all=True)

    # 4. Execute (git worktree isolation is handled by the pipeline engine/scheduler)
    console.print("[bold green]Handing over to Execution Pipeline...[/bold green]")
    await run_execution(unattended=True)


@squad_app.command(
    name="orchestrate", help="Run the full Scrum Master deterministic loop (PRD -> Map -> Execute)."
)
def squad_orchestrate_cmd(prd_path: str = typer.Argument(..., help="Path to the PRD file")) -> None:
    try:
        asyncio.run(run_orchestrate(prd_path))
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Orchestration failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e
