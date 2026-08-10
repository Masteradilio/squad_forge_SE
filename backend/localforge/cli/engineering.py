# ruff: noqa: B008, UP047
"""CLI adapters for the shared DPC-001..003 continuity service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import typer
from localforge.models.enums import ActionKind, ExecutionMode
from localforge.services.engineering import EngineeringContinuityService
from localforge.services.tenant_context import TenantContext, bind_context, normalize_tenant_id, reset_context
from localforge.storage import UnitOfWork, db_manager
from localforge.storage.bootstrap import bootstrap_database
from rich.console import Console

console = Console()
engineering_app = typer.Typer(help="Manage durable engineering sessions, goals, turns, and profiles.")
session_app = typer.Typer(help="Manage durable engineering sessions.")
goal_app = typer.Typer(help="Create and revise engineering goals.")
turn_app = typer.Typer(help="Admit and inspect immutable engineering turns.")
profile_app = typer.Typer(help="Manage and evaluate execution profiles.")
engineering_app.add_typer(session_app, name="session")
engineering_app.add_typer(goal_app, name="goal")
engineering_app.add_typer(turn_app, name="turn")
engineering_app.add_typer(profile_app, name="profile")

T = TypeVar("T")


def _jsonable(value: Any) -> Any:
    """Convert nested domain models to JSON without losing list semantics."""
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _json(value: Any) -> None:
    console.print_json(json.dumps(_jsonable(value), default=str))


async def _execute(
    tenant_id: str,
    operation: Callable[[EngineeringContinuityService], Awaitable[T]],
) -> T:
    try:
        normalized = normalize_tenant_id(tenant_id)
    except Exception as exc:
        raise typer.BadParameter(str(exc), param_hint="--tenant-id") from exc
    token = bind_context(TenantContext(tenant_id=normalized, user_id="local-cli"))
    try:
        await bootstrap_database(db_manager)
        async with UnitOfWork(db_manager) as uow:
            assert uow.engineering is not None
            return await operation(uow.engineering)
    finally:
        reset_context(token)


@session_app.command("create")
def create_session(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    title: str = typer.Option("Engineering Session", "--title"),
    default_model: str | None = typer.Option(None, "--model"),
    max_turns: int | None = typer.Option(None, "--max-turns"),
    max_wall_seconds: float | None = typer.Option(None, "--max-wall-seconds"),
    max_retries: int = typer.Option(0, "--max-retries"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    """Create a durable engineering session."""
    _json(
        asyncio.run(
            _execute(
                tenant_id,
                lambda service: service.create_session(
                    project_id=project_id,
                    title=title,
                    default_model=default_model,
                    max_turns=max_turns,
                    max_wall_seconds=max_wall_seconds,
                    max_retries=max_retries,
                ),
            )
        )
    )


@session_app.command("list")
def list_sessions(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    """List sessions visible to the current tenant."""
    _json(asyncio.run(_execute(tenant_id, lambda service: service.list_sessions(project_id))))


@session_app.command("get")
def get_session(
    session_id: str = typer.Argument(...),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    """Get one session."""
    session = asyncio.run(_execute(tenant_id, lambda service: service.get_session(session_id)))
    if session is None:
        raise typer.BadParameter("engineering session not found")
    _json(session)


@session_app.command("close")
def close_session(
    session_id: str = typer.Argument(...),
    result: str | None = typer.Option(None, "--result"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    """Complete a session."""
    _json(asyncio.run(_execute(tenant_id, lambda service: service.close_session(session_id, result=result))))


@session_app.command("pause")
def pause_session(
    session_id: str = typer.Argument(...),
    reason: str = typer.Option("user_pause", "--reason"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(asyncio.run(_execute(tenant_id, lambda service: service.pause_session(session_id, reason=reason))))


@session_app.command("resume")
def resume_session(
    session_id: str = typer.Argument(...),
    reason: str = typer.Option("user_resume", "--reason"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(asyncio.run(_execute(tenant_id, lambda service: service.resume_session(session_id, reason=reason))))


@session_app.command("cancel")
def cancel_session(
    session_id: str = typer.Argument(...),
    reason: str = typer.Option("user_cancel", "--reason"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(asyncio.run(_execute(tenant_id, lambda service: service.cancel_session(session_id, reason=reason))))


@goal_app.command("create")
def create_goal(
    session_id: str = typer.Option(..., "--session-id"),
    objective: str = typer.Option(..., "--objective"),
    acceptance_criteria: list[str] = typer.Option([], "--criterion"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(
        asyncio.run(
            _execute(
                tenant_id,
                lambda service: service.create_goal(
                    session_id=session_id,
                    objective=objective,
                    acceptance_criteria=acceptance_criteria,
                ),
            )
        )
    )


@goal_app.command("revise")
def revise_goal(
    goal_id: str = typer.Argument(...),
    objective: str = typer.Option(..., "--objective"),
    acceptance_criteria: list[str] = typer.Option([], "--criterion"),
    expected_revision: int | None = typer.Option(None, "--expected-revision"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(
        asyncio.run(
            _execute(
                tenant_id,
                lambda service: service.revise_goal(
                    goal_id,
                    objective,
                    acceptance_criteria,
                    expected_revision=expected_revision,
                ),
            )
        )
    )


@turn_app.command("admit")
def admit_turn(
    session_id: str = typer.Option(..., "--session-id"),
    input_text: str = typer.Option("", "--input"),
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    model: str | None = typer.Option(None, "--model"),
    kind: str = typer.Option("USER", "--kind"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    from localforge.models.enums import EngineeringTurnKind

    _json(
        asyncio.run(
            _execute(
                tenant_id,
                lambda service: service.admit_turn(
                    session_id=session_id,
                    input_text=input_text,
                    idempotency_key=idempotency_key,
                    model=model,
                    kind=EngineeringTurnKind(kind.upper()),
                ),
            )
        )
    )


@turn_app.command("timeline")
def timeline(
    session_id: str = typer.Argument(...),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(asyncio.run(_execute(tenant_id, lambda service: service.timeline(session_id))))


@profile_app.command("set")
def set_profile(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    mode: str = typer.Option("ASK", "--mode"),
    session_id: str | None = typer.Option(None, "--session-id"),
    name: str = typer.Option("default", "--name"),
    trust: str = typer.Option("standard", "--trust"),
    tool_policies_json: str = typer.Option("{}", "--tool-policies"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    try:
        policies = json.loads(tool_policies_json)
        if not isinstance(policies, dict):
            raise ValueError("tool policies must be a JSON object")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--tool-policies") from exc
    _json(
        asyncio.run(
            _execute(
                tenant_id,
                lambda service: service.create_or_update_profile(
                    project_id=project_id,
                    session_id=session_id,
                    name=name,
                    trust=trust,
                    mode=ExecutionMode(mode.upper()),
                    tool_policies=policies,
                ),
            )
        )
    )


@profile_app.command("list")
def list_profiles(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    _json(asyncio.run(_execute(tenant_id, lambda service: service.list_profiles(project_id))))


@profile_app.command("evaluate")
def evaluate_profile(
    project_id: int = typer.Option(..., "--project-id", "-p"),
    action_kind: str = typer.Option(..., "--action"),
    payload_json: str = typer.Option("{}", "--payload"),
    session_id: str | None = typer.Option(None, "--session-id"),
    turn_id: str | None = typer.Option(None, "--turn-id"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    tenant_id: str = typer.Option("local", "--tenant-id"),
) -> None:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(str(exc), param_hint="--payload") from exc
    _json(
        asyncio.run(
            _execute(
                tenant_id,
                lambda service: service.evaluate_action(
                    project_id=project_id,
                    action_kind=ActionKind(action_kind),
                    payload=payload,
                    session_id=session_id,
                    turn_id=turn_id,
                    idempotency_key=idempotency_key,
                ),
            )
        )
    )
