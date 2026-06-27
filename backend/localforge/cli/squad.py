import asyncio
import os
import typer
from localforge.storage import UnitOfWork, db_manager
from localforge.models import domain
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
                route_val = await uow.routing.get_model_for_role(project.id, meta.default_agent_role)
                if route_val:
                    model_profile_id = route_val
                    routes = await uow.routing.list_routes(project.id)
                    for r in routes:
                        if r.role == meta.default_agent_role:
                            provider = r.provider
                            break
                else:
                    if meta.seniority_class in (domain.SeniorityClass.CHIEF_ONLY, domain.SeniorityClass.CHIEF_LED):
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
                provider
            )

        console.print(table)


@squad_app.command(name="composition", help="Show the current squad composition and routing model assignment.")
def squad_composition_cmd() -> None:
    try:
        asyncio.run(run_squad_composition())
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Command failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e
