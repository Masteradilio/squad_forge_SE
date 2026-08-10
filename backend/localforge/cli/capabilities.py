"""CLI adapters for the shared model/Skill/Automation services."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from localforge.models import domain
from localforge.models.enums import AutomationStatus
from localforge.services.tenant_context import TenantContext, bind_context, normalize_tenant_id, reset_context
from localforge.storage import UnitOfWork, db_manager
from localforge.storage.bootstrap import bootstrap_database

capabilities_app = typer.Typer(help="Manage model verification, Skill bindings, and Automations.")
models_app = typer.Typer(help="Inspect the OmniRoute model catalog.")
automations_app = typer.Typer(help="Manage durable Automations.")
capabilities_app.add_typer(models_app, name="models")
capabilities_app.add_typer(automations_app, name="automations")


def _print(value: Any) -> None:
    if isinstance(value, list):
        value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    elif hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, default=str))


def _run(tenant_id: str, operation: Any) -> Any:
    normalized = normalize_tenant_id(tenant_id)
    token = bind_context(TenantContext(tenant_id=normalized, user_id="local-cli"))
    try:

        async def execute() -> Any:
            await bootstrap_database(db_manager)
            async with UnitOfWork(db_manager) as uow:
                return await operation(uow)

        return asyncio.run(execute())
    finally:
        reset_context(token)


@models_app.command("discover")
def discover_models(project_id: int = typer.Option(..., "--project-id"), tenant_id: str = typer.Option("local", "--tenant-id")) -> None:
    _print(_run(tenant_id, lambda uow: uow.model_catalog.discover(project_id)))


@models_app.command("list")
def list_models(project_id: int = typer.Option(..., "--project-id"), tenant_id: str = typer.Option("local", "--tenant-id")) -> None:
    _print(_run(tenant_id, lambda uow: uow.model_catalog.list_entries(project_id)))


@models_app.command("probe")
def probe_model(
    project_id: int = typer.Option(..., "--project-id"), model_name: str = typer.Option(..., "--model"), tenant_id: str = typer.Option("local", "--tenant-id")
) -> None:
    _print(_run(tenant_id, lambda uow: uow.model_catalog.probe(project_id, model_name)))


@automations_app.command("create")
def create_automation(
    project_id: int = typer.Option(..., "--project-id"),
    name: str = typer.Option(..., "--name"),
    objective: str = typer.Option(..., "--objective"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    async def op(uow: Any) -> Any:
        return await uow.automations.create(domain.Automation(project_id=project_id, name=name, goal_template={"objective": objective}))

    _print(_run(tenant_id, op))


@automations_app.command("run")
def run_automation(
    automation_id: str = typer.Argument(...),
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _print(_run(tenant_id, lambda uow: uow.automations.trigger(automation_id, idempotency_key)))


@automations_app.command("pause")
def pause_automation(automation_id: str = typer.Argument(...), tenant_id: str = typer.Option("local", "--tenant-id")) -> None:
    _print(_run(tenant_id, lambda uow: uow.automations.set_status(automation_id, AutomationStatus.PAUSED)))
