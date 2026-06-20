import asyncio
import copy
import os
from typing import Any, cast

import typer
import yaml
from rich.console import Console

try:
    import git
except ImportError:
    git = None  # type: ignore[assignment]

from localforge.core.templates import DEFAULT_CONFIG_TEMPLATE, DEFAULT_POLICY_TEMPLATE
from localforge.models import domain
from localforge.storage import UnitOfWork, bootstrap_database, db_manager

console = Console()


def get_git_info() -> tuple[str, str]:
    """Retrieve current git default branch and remote URL if applicable."""
    default_branch = "main"
    remote_url = ""
    if git is not None:
        try:
            repo = git.Repo(os.getcwd(), search_parent_directories=True)
            try:
                default_branch = repo.active_branch.name
            except Exception:
                pass

            if repo.remotes:
                remote_url = repo.remotes.origin.url
        except Exception:
            pass
    return default_branch, remote_url


async def run_init() -> None:
    """Async task executor for workspace initialization."""
    cwd = os.getcwd()
    project_name = os.path.basename(cwd)
    lf_dir = os.path.join(cwd, ".localforge")

    console.print(f"[bold blue]Initializing LocalForge OS workspace at:[/bold blue] {cwd}")

    # 1. Idempotency Check
    if os.path.exists(lf_dir):
        console.print(
            "[yellow]Warning: .localforge workspace directory already exists. "
            "Skipping folder creation.[/yellow]"
        )
    else:
        # 2. Create Directory Structure
        subdirs = ["policies", "skills", "memory", "artifacts", "runs", "logs"]
        os.makedirs(lf_dir, exist_ok=True)
        for subdir in subdirs:
            os.makedirs(os.path.join(lf_dir, subdir), exist_ok=True)
        console.print("[green]Created .localforge directory layout.[/green]")

    # 3. Get Git settings
    default_branch, remote_url = get_git_info()

    # 4. Create config.yaml if it does not exist
    config_path = os.path.join(lf_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_data = copy.deepcopy(DEFAULT_CONFIG_TEMPLATE)
        config_data["project"]["name"] = project_name
        config_data["git"]["default_branch"] = default_branch
        config_data["git"]["remote_url"] = remote_url

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, default_flow_style=False)
        console.print(f"[green]Created default config at:[/green] {config_path}")

    # 5. Create default policy default.yaml if it does not exist
    policy_path = os.path.join(lf_dir, "policies", "default.yaml")
    if not os.path.exists(policy_path):
        with open(policy_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_POLICY_TEMPLATE, f, default_flow_style=False)
        console.print(f"[green]Created conservative security policy at:[/green] {policy_path}")

    # 6. Bootstrap database
    console.print("[blue]Bootstrapping local database...[/blue]")
    await bootstrap_database(db_manager)

    # 7. Create/Register project record using UnitOfWork
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.audits is not None

        existing_proj = await uow.projects.get_project_by_path(cwd)
        if existing_proj:
            console.print(
                f"[yellow]Project already registered in database "
                f"with ID: {existing_proj.id}[/yellow]"
            )
        else:
            proj_data = domain.Project(
                name=project_name,
                root_path=cwd,
                default_branch=default_branch,
                remote_url=remote_url or None,
                localforge_config_path=config_path,
            )
            new_proj = await uow.projects.create_project(proj_data)
            assert new_proj.id is not None

            # Create default policy entry in the database
            policy_obj = domain.Policy(
                project_id=new_proj.id,
                name="default",
                rules=cast(dict[str, Any], DEFAULT_POLICY_TEMPLATE["policy"]),
            )
            await uow.audits.create_policy(policy_obj)

            # Record initialization event in audit log
            audit_event = domain.AuditEvent(
                project_id=new_proj.id,
                actor_type=domain.AuditEventActorType.USER,
                actor_id="system-cli",
                event_type=domain.AuditEventType.SYSTEM_EVENT,
                payload_redacted={"action": "localforge_init", "path": cwd},
            )
            await uow.audits.append_audit_event(audit_event)

            console.print(
                f"[bold green]Project '{project_name}' successfully "
                f"initialized and registered (ID: {new_proj.id})![/bold green]"
            )


def init_cmd() -> None:
    """Initialize a new LocalForge workspace in the current directory."""
    try:
        asyncio.run(run_init())
    except Exception as e:
        console.print(f"[bold red]Initialization failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e
