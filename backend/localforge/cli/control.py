import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

import typer
from localforge.core.config import load_config
from localforge.llm.openai_compatible import OpenAICompatibleProvider
from localforge.models.enums import RunStatus, TaskRunStatus
from localforge.skills import SkillRegistry
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console
from rich.table import Table

console = Console()


async def _current_project(uow: UnitOfWork):
    assert uow.projects is not None
    project = await uow.projects.get_project_by_path(os.getcwd())
    if not project:
        console.print(
            "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
        )
        raise typer.Exit(code=1)
    return project


async def _latest_run(project_id: int, uow: UnitOfWork):
    assert uow.executions is not None
    runs = await uow.executions.list_runs_for_project(project_id)
    if not runs:
        console.print("[yellow]No runs recorded yet.[/yellow]")
        raise typer.Exit(code=1)
    return runs[0]


async def _set_latest_run_status(status: RunStatus) -> None:
    async with UnitOfWork(db_manager) as uow:
        assert uow.executions is not None
        assert uow.tasks is not None
        project = await _current_project(uow)
        assert project.id is not None
        run = await _latest_run(project.id, uow)
        if status == RunStatus.CANCELLED and run.id is not None:
            ended_at = datetime.now(UTC)
            for task_run in await uow.tasks.list_runs_for_run(run.id):
                if task_run.status not in {TaskRunStatus.PENDING, TaskRunStatus.RUNNING}:
                    continue
                task_run.status = TaskRunStatus.CANCELLED
                task_run.ended_at = ended_at
                task_run.final_summary = "Cancelled with parent run by operator."
                await uow.tasks.update_task_run(task_run)
        run.status = status
        if status in {RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.COMPLETED}:
            run.ended_at = datetime.now(UTC)
        await uow.executions.update_run(run)
        console.print(f"[green]Run {run.id} set to {status.value}.[/green]")


def pause_cmd() -> None:
    """Pause the latest run in the current workspace."""
    asyncio.run(_set_latest_run_status(RunStatus.PAUSED))


def resume_cmd() -> None:
    """Resume the latest paused run in the current workspace."""
    asyncio.run(_set_latest_run_status(RunStatus.RUNNING))


def stop_cmd() -> None:
    """Stop the latest run in the current workspace."""
    asyncio.run(_set_latest_run_status(RunStatus.CANCELLED))


tasks_app = typer.Typer(help="List and inspect LocalForge tasks.")
task_app = typer.Typer(help="Inspect a single LocalForge task.")
models_app = typer.Typer(help="Inspect local model configuration.")
chief_engineer_app = typer.Typer(help="Run scarce paid Chief Engineer gates.")
skills_app = typer.Typer(help="Inspect workspace skills.")
safety_app = typer.Typer(help="Inspect safety policy and approval state.")


@tasks_app.command("list")
def tasks_list_cmd(json_output: bool = typer.Option(False, "--json")) -> None:
    """List tasks for the current workspace."""

    async def run() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.tasks is not None
            project = await _current_project(uow)
            assert project.id is not None
            tasks = await uow.tasks.list_tasks_for_project(project.id)
            payload = [task.model_dump(mode="json") for task in tasks]
            if json_output:
                sys.stdout.write(json.dumps(payload, indent=2))
                return
            table = Table(title="LocalForge Tasks")
            table.add_column("Key")
            table.add_column("Title")
            table.add_column("Status")
            table.add_column("Risk")
            for task in tasks:
                table.add_row(task.key, task.title, task.status.value, task.risk_level)
            console.print(table)

    asyncio.run(run())


@task_app.command("get")
def task_get_cmd(key: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Get one task by key."""

    async def run() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.tasks is not None
            task = await uow.tasks.get_task_by_key(key)
            if not task:
                console.print(f"[bold red]Task not found: {key}[/bold red]")
                raise typer.Exit(code=1)
            payload = task.model_dump(mode="json")
            if json_output:
                sys.stdout.write(json.dumps(payload, indent=2))
                return
            console.print_json(json.dumps(payload))

    asyncio.run(run())


def logs_cmd(limit: int = typer.Option(25, "--limit")) -> None:
    """Print recent audit log events for the current workspace."""

    async def run() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.audits is not None
            project = await _current_project(uow)
            assert project.id is not None
            events = await uow.audits.list_audit_events_for_project(project.id)
            for event in events[:limit]:
                payload = json.dumps(
                    event.payload_redacted,
                    ensure_ascii=True,
                    sort_keys=True,
                    default=str,
                )
                console.print(
                    f"{event.created_at.isoformat()} {event.event_type.value} "
                    f"{payload}"
                )

    asyncio.run(run())


def replay_cmd(run_id: int, limit: int = typer.Option(100, "--limit")) -> None:
    """Export replay events for a run."""

    async def run() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.audits is not None
            project = await _current_project(uow)
            assert project.id is not None
            timeline = await uow.audits.export_run_replay(project.id, run_id, limit=limit)
            sys.stdout.write(json.dumps(timeline, indent=2))

    asyncio.run(run())


@models_app.command("list")
def models_list_cmd() -> None:
    """List models visible through the local model provider."""

    async def run() -> None:
        config = load_config()
        provider = OpenAICompatibleProvider(
            base_url=config.models.base_url,
            api_key=config.models.api_key,
            default_model=config.models.default_model,
        )
        console.print_json(
            json.dumps(
                {
                    "provider": config.models.provider,
                    "base_url": config.models.base_url,
                    "default_model": config.models.default_model,
                    "models": await provider.list_models(),
                }
            )
        )

    asyncio.run(run())


@models_app.command("paid-calls")
def models_paid_calls_cmd() -> None:
    """List Chief Engineer paid model calls for the current project."""

    async def run() -> None:
        config = load_config()
        async with UnitOfWork(db_manager) as uow:
            assert uow.model_calls is not None
            project = await _current_project(uow)
            assert project.id is not None
            calls = await uow.model_calls.list_calls(project_id=project.id)
            console.print_json(
                json.dumps(
                    {
                        "provider": config.chief_engineer.provider,
                        "model": config.chief_engineer.model,
                        "enabled": config.chief_engineer.enabled,
                        "api_key_configured": bool(config.chief_engineer.api_key),
                        "budget": {
                            "max_paid_calls": config.budgets.max_paid_calls,
                            "max_paid_input_tokens": config.budgets.max_paid_input_tokens,
                            "max_paid_output_tokens": config.budgets.max_paid_output_tokens,
                            "max_paid_usd": config.budgets.max_paid_usd,
                        },
                        "calls": [call.model_dump(mode="json") for call in calls],
                    }
                )
            )

    asyncio.run(run())


@chief_engineer_app.command("freeze-contract")
def chief_engineer_freeze_contract_cmd(
    contract_path: str = typer.Option(
        ".localforge/contracts/architecture_contract.json",
        "--contract",
        help="Path to architecture contract relative to the current workspace.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Review and freeze the imported architecture contract."""

    async def run() -> None:
        from localforge.chief_engineer.service import ChiefEngineerService
        from localforge.llm.factory import build_chief_engineer_provider
        from localforge.prd.contracts import ArchitectureContract

        config = load_config()
        path = os.path.abspath(contract_path)
        if not os.path.isfile(path):
            console.print(f"[bold red]Architecture contract not found:[/bold red] {contract_path}")
            raise typer.Exit(code=1)
        contract = ArchitectureContract.model_validate_json(open(path, encoding="utf-8").read())
        if not config.chief_engineer.model:
            console.print("[bold red]The OmniRoute Chief Engineer model is not configured.[/bold red]")
            raise typer.Exit(code=1)
        provider = build_chief_engineer_provider(config)
        async with UnitOfWork(db_manager) as uow:
            project = await _current_project(uow)
            assert project.id is not None
            review = await ChiefEngineerService(uow).review_contract(
                project_id=project.id,
                run_id=None,
                contract=contract,
                provider=provider,
                model=config.chief_engineer.model,
            )
            payload = review.model_dump(mode="json")
            if json_output:
                sys.stdout.write(json.dumps(payload, indent=2))
                return
            console.print_json(json.dumps(payload))

    asyncio.run(run())


@skills_app.command("list")
def skills_list_cmd() -> None:
    """List built-in and local workspace skills."""

    async def run() -> None:
        async with UnitOfWork(db_manager) as uow:
            project = await _current_project(uow)
            skills = [
                skill.model_dump(mode="json")
                for skill in SkillRegistry(project.root_path).load_all()
            ]
            console.print_json(json.dumps(skills))

    asyncio.run(run())


@safety_app.command("status")
def safety_status_cmd() -> None:
    """Show safety policy and pending approvals."""

    async def run() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.audits is not None
            assert uow.safety is not None
            project = await _current_project(uow)
            assert project.id is not None
            policy = await uow.audits.get_project_policy(project.id, "default")
            approvals = await uow.safety.list_pending_approvals(project.id)
            payload: dict[str, Any] = {
                "policy": policy.model_dump(mode="json") if policy else None,
                "pending_approvals": [approval.model_dump(mode="json") for approval in approvals],
            }
            console.print_json(json.dumps(payload))

    asyncio.run(run())
