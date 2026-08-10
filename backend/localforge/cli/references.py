# ruff: noqa: B008
"""CLI for reference ingestion and lexical CodeRAG decisions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from localforge.services.tenant_context import TenantContext, bind_context, normalize_tenant_id, reset_context
from localforge.storage import UnitOfWork, db_manager
from localforge.storage.bootstrap import bootstrap_database

references_app = typer.Typer(help="Ingest references, search citations, and freeze ProductBlueprints.")


def _json(value: Any) -> None:
    if isinstance(value, list):
        value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    elif hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, default=str))


def _run(tenant_id: str, operation: Any) -> Any:
    token = bind_context(TenantContext(tenant_id=normalize_tenant_id(tenant_id), user_id="local-cli"))
    try:

        async def execute() -> Any:
            await bootstrap_database(db_manager)
            async with UnitOfWork(db_manager) as uow:
                return await operation(uow.references)

        return asyncio.run(execute())
    finally:
        reset_context(token)


@references_app.command("ingest")
def ingest(
    project_id: int = typer.Option(..., "--project-id"),
    path: Path = typer.Option(..., "--path", exists=True),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(_run(tenant_id, lambda service: service.ingest_file(project_id=project_id, path=str(path))))


@references_app.command("search")
def search(
    project_id: int = typer.Option(..., "--project-id"), query: str = typer.Option(..., "--query"), tenant_id: str = typer.Option("local", "--tenant-id")
) -> None:
    _json(_run(tenant_id, lambda service: service.search(project_id=project_id, query=query)))


@references_app.command("decide")
def decide(
    project_id: int = typer.Option(..., "--project-id"),
    query: str = typer.Option(..., "--query"),
    summary: str = typer.Option(..., "--summary"),
    chunks: list[str] = typer.Option(..., "--chunk"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(_run(tenant_id, lambda service: service.decide(project_id=project_id, query=query, summary=summary, selected_chunk_ids=chunks)))
