import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer
from localforge.core.config import LocalForgeConfig, load_config
from localforge.control_plane import (
    ControlPlaneKernel,
    ControlPlaneStore,
    goal_id_for_project,
    state_path_for_goal,
)
from localforge.llm.base import LLMConnectionError, LLMHTTPError, LLMTimeoutError
from localforge.llm.factory import build_chief_engineer_provider
from localforge.models import domain
from localforge.models.enums import RunMode, RunStatus, TaskRunStatus, TaskStatus
from localforge.services.pricing import is_free_gateway_model
from localforge.services.scheduler import Scheduler
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console

console = Console()


# LocalForge OS — direct the LLM/log diagnostics to stderr so the
# Rich console can still print user-facing status while we keep the
# full event stream grep-able from the run artefacts. Operators looking
# at ``run_summary.md`` rely on these lines to retrace the expensive
# local Ollama decisions and the Chief Engineer fallback path.
logging.basicConfig(
    level=os.getenv("LOCALFORGE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("localforge")


def _sqlite_monitor_snapshot(
    db_url: str, *, run_id: int, project_id: int
) -> tuple[RunStatus, str | None, list[str]] | None:
    """Read run progress without opening an ORM transaction.

    The CLI monitor is observability only. A SQLAlchemy session here can open a
    read transaction while the scheduler is committing a write transaction,
    which is enough to deadlock SQLite on Windows. A short query-only
    connection keeps monitoring outside the scheduler's write path.
    """
    prefix = "sqlite+aiosqlite:///"
    if not db_url.startswith(prefix):
        return None
    db_path = db_url[len(prefix) :]
    if db_path.startswith("/") and len(db_path) > 2 and db_path[2] == ":":
        db_path = db_path[1:]
    connection = sqlite3.connect(db_path, timeout=0.5)
    try:
        connection.execute("PRAGMA query_only=ON")
        run_row = connection.execute(
            "SELECT status, summary FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            return None
        running_statuses = {
            TaskStatus.CLAIMED.value,
            TaskStatus.PLANNING.value,
            TaskStatus.IMPLEMENTING.value,
            TaskStatus.TESTING.value,
            TaskStatus.REPAIRING.value,
        }
        task_rows = connection.execute(
            "SELECT key, status FROM tasks WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
        running_tasks = [
            f"{key} ({status})" for key, status in task_rows if status in running_statuses
        ]
        return RunStatus(str(run_row[0])), run_row[1], running_tasks
    finally:
        connection.close()


def _task_requires_chief(task: domain.Task) -> bool:
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    contract = metadata.get("task_contract")
    if not isinstance(contract, dict):
        return False
    return bool(
        contract.get("visual_required")
        or contract.get("seniority_class") in {"chief_only", "chief_led"}
    )


async def _run_chief_preflight(
    config: LocalForgeConfig,
    ready_tasks: list[domain.Task],
) -> str | None:
    """Probe the configured Chief once before a paid, Chief-dependent run.

    Without this guard, an exhausted provider is rediscovered independently by
    every task and the scheduler spends the whole run repeating the same 402.
    The probe is deliberately tiny and bounded; it is a readiness check, not a
    second implementation request.
    """
    if not any(_task_requires_chief(task) for task in ready_tasks):
        return None
    chief = config.chief_engineer
    if not chief.enabled or not chief.model:
        return "Chief Engineer is required by the ready task contracts but is not configured."
    if chief.provider.lower() != "omniroute" and not chief.api_key:
        return "Chief Engineer is required by the ready task contracts but has no API key."
    try:
        provider = build_chief_engineer_provider(config)
        # Readiness must prove the configured primary provider itself. Using
        # the paid fallback wrapper here can turn a slow-but-healthy primary
        # into a false OpenRouter credit failure before task execution starts.
        probe_provider = getattr(provider, "primary", provider)
        list_models = getattr(probe_provider, "list_models", None)
        # Do not silently downgrade a Chief request to the generic ``auto``
        # alias.  That alias can select an unsuitable free route and turn a
        # healthy OmniRoute gateway into a false task failure.  The configured
        # bounded ladder is the source of truth; if none is healthy, fail the
        # preflight explicitly and let the operator retry later.
        probe_models = list(dict.fromkeys([chief.model, *chief.fallback_models]))
        if callable(list_models):
            available_models = await asyncio.wait_for(list_models(), timeout=15.0)
            if not available_models:
                return (
                    "Chief Engineer provider returned no available models for its "
                    "configured endpoint."
                )
            # The live gateway catalog is the source of truth for free/freemium
            # availability. Keep configured routes first, then append a bounded
            # set of explicitly free routes so stale aliases do not block a
            # healthy OmniRoute deployment.
            discovered_free_models = [
                model
                for model in available_models
                if isinstance(model, str) and is_free_gateway_model(model)
            ][:8]
            probe_models = list(dict.fromkeys([*probe_models, *discovered_free_models]))
            if not any(model in available_models for model in probe_models):
                return (
                    f"No Chief Engineer readiness model from {probe_models!r} is available at "
                    f"provider '{chief.provider}' endpoint. Available models: "
                    f"{', '.join(available_models[:20])}."
                )
        if chief.provider.lower() == "omniroute":
            # A readiness probe is intentionally much smaller than a task. A
            # free route that cannot produce a tiny structured response within
            # this window must not hold an unattended run for the full task
            # timeout; the bounded route ladder/recovery rounds remain the
            # source of resilience.
            request_timeout = min(max(float(chief.timeout), 20.0), 35.0)
        else:
            # A paid primary must get enough time to produce its structured
            # readiness response. Keep the probe bounded, but do not reject a
            # healthy model solely because its configured task timeout is larger.
            request_timeout = min(max(float(chief.timeout), 45.0), 120.0)
        try:
            configured_probe_timeout = float(
                os.getenv("LOCALFORGE_CHIEF_PREFLIGHT_TIMEOUT", "30")
            )
        except ValueError:
            configured_probe_timeout = 50.0
        probe_timeout = min(request_timeout + 5.0, max(configured_probe_timeout, 5.0))
        try:
            max_attempts = max(
                1,
                int(os.getenv("LOCALFORGE_CHIEF_PREFLIGHT_MAX_ATTEMPTS", "2")),
            )
        except ValueError:
            max_attempts = 2
        try:
            gateway_rounds = min(
                3,
                max(1, int(os.getenv("LOCALFORGE_CHIEF_PREFLIGHT_GATEWAY_ROUNDS", "2"))),
            )
        except ValueError:
            gateway_rounds = 2
        try:
            gateway_retry_delay = min(
                30.0,
                max(0.0, float(os.getenv("LOCALFORGE_CHIEF_PREFLIGHT_GATEWAY_RETRY_DELAY", "2"))),
            )
        except ValueError:
            gateway_retry_delay = 2.0

        errors: list[str] = []
        gateway_outage_limit = min(4, max(1, len(probe_models)))
        for gateway_round in range(gateway_rounds):
            gateway_outage_count = 0
            gateway_failed_models: set[str] = set()
            gateway_outage_seen = False
            for attempt in range(max_attempts):
                transient_seen = False
                for probe_model in probe_models:
                    if callable(list_models) and probe_model not in available_models:
                        continue
                    if probe_model in gateway_failed_models:
                        continue
                    try:
                        response = await asyncio.wait_for(
                            probe_provider.chat_completion(
                                [
                                    {
                                        "role": "system",
                                        "content": (
                                            "You are a provider readiness probe. Return only valid JSON "
                                            "with one concrete action: "
                                            '{"actions":[{"kind":"write_file","path":"probe.txt",'
                                            '"content":"ok"}]}'
                                        ),
                                    },
                                    {"role": "user", "content": "Return the structured probe now."},
                                ],
                                stream=False,
                                response_schema={"type": "object"},
                                timeout=min(float(chief.timeout), request_timeout),
                                model=probe_model,
                            ),
                            timeout=probe_timeout,
                        )
                        if not isinstance(response, str) or not response.strip():
                            raise ValueError("empty response")
                        probe_payload = json.loads(response)
                        if (
                            not isinstance(probe_payload, dict)
                            or not isinstance(probe_payload.get("actions"), list)
                            or not probe_payload["actions"]
                        ):
                            raise ValueError("expected a non-empty actions array")
                        if chief.provider.lower() == "omniroute":
                            os.environ["LOCALFORGE_CHIEF_MODEL"] = probe_model
                        return None
                    except Exception as exc:
                        errors.append(
                            f"round={gateway_round + 1} attempt={attempt + 1} "
                            f"{probe_model}: {exc}"
                        )
                        if _is_gateway_upstream_outage(exc):
                            gateway_outage_count += 1
                            gateway_failed_models.add(probe_model)
                            if gateway_outage_count >= gateway_outage_limit:
                                gateway_outage_seen = True
                                break
                        if _is_transient_probe_error(exc):
                            transient_seen = True
                if gateway_outage_seen:
                    break
                if transient_seen and attempt + 1 < max_attempts:
                    await asyncio.sleep(2.0)

            if gateway_outage_seen and gateway_round + 1 < gateway_rounds:
                if gateway_retry_delay:
                    await asyncio.sleep(gateway_retry_delay)
                continue
            if gateway_outage_seen:
                return (
                    "OmniRoute gateway is reachable, but its upstream routes are unavailable; "
                    f"preflight stopped after {gateway_rounds} bounded round(s) with "
                    f"{gateway_outage_limit} distinct gateway failures per round: "
                    + "; ".join(errors[-2:])
                )
            return "Chief Engineer readiness probe exhausted provider ladder: " + "; ".join(
                errors
            )

        return "Chief Engineer readiness probe exhausted provider ladder: " + "; ".join(errors)
    except Exception as exc:
        return f"Chief Engineer readiness probe failed: {exc}"


def _is_transient_probe_error(error: Exception) -> bool:
    if isinstance(error, (LLMConnectionError, LLMTimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(error, LLMHTTPError):
        return error.status_code == 429 or error.status_code >= 500
    message = str(error).lower()
    return any(marker in message for marker in ("429", "rate limit", "timeout", "temporary"))


def _is_gateway_upstream_outage(error: Exception) -> bool:
    """Identify gateway responses that indicate an upstream-wide outage.

    A 500/502 from OmniRoute can contain ``fetch failed`` or a connect/stream
    timeout while the gateway itself remains healthy. Retrying every configured
    alias in that state only burns the run budget; the pre-flight skips failed
    aliases, tests at most four distinct routes per round, and allows a small
    bounded recovery window before reporting an actionable blocker.
    """
    if not isinstance(error, LLMHTTPError) or error.status_code < 500:
        return False
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("fetch failed", "connect timeout", "stream ended", "bad gateway")
    )


async def run_execution(unattended: bool) -> None:
    cwd = os.getcwd()
    lf_dir = os.path.join(cwd, ".localforge")
    if not os.path.exists(lf_dir):
        console.print(
            "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
        )

    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.executions is not None
        assert uow.tasks is not None

        project = await uow.projects.get_project_by_path(cwd)
        if not project:
            console.print(
                "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
            )
            raise typer.Exit(code=1)
        assert project.id is not None

        tasks = await uow.tasks.list_tasks_for_project(project.id)
        ready_tasks = [t for t in tasks if t.status == TaskStatus.READY]

        if not ready_tasks:
            console.print(
                "[yellow]No tasks in READY status found. "
                "Run 'localforge plan' to approve plans first.[/yellow]"
            )
            return

        # Create a new Run record
        mode = RunMode.UNATTENDED if unattended else RunMode.INTERACTIVE
        run_data = domain.Run(
            project_id=project.id,
            mode=mode,
            status=RunStatus.PENDING,
            initiated_by="cli",
            started_at=datetime.now(UTC),
            resource_limits=_run_resource_limits(),
        )
        run = await uow.executions.create_run(run_data)
        assert run.id is not None
        assert uow.session is not None
        await uow.session.commit()

        console.print(
            f"[bold green]Starting Run {run.id}[/bold green] in [cyan]{mode.value}[/cyan] mode..."
        )

    assert project.id is not None
    assert run.id is not None
    project_id = project.id
    run_id = run.id
    try:
        config = load_config()
        max_parallel_tasks = config.budgets.max_parallel_tasks
        monitor_timeout = config.budgets.max_run_time + 5.0
    except Exception:
        max_parallel_tasks = 2
        monitor_timeout = 3605.0

    preflight_error = await _run_chief_preflight(config, ready_tasks)
    if preflight_error:
        async with UnitOfWork(db_manager) as uow:
            assert uow.executions is not None
            blocked_run = await uow.executions.get_run(run_id)
            if blocked_run:
                blocked_run.status = RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW
                blocked_run.summary = preflight_error
                blocked_run.ended_at = datetime.now(UTC)
                await uow.executions.update_run(blocked_run)
        console.print(f"[bold yellow]Run blocked before task execution:[/bold yellow] {preflight_error}")
        return

    # Initialize and start Scheduler in the background
    scheduler = Scheduler(
        project_id=project_id,
        run_id=run_id,
        db_manager=db_manager,
        loop_interval=0.2,
        max_parallel_tasks=max_parallel_tasks,
        execute_pipeline=True,
    )
    await scheduler.start()

    async def monitor_run() -> None:
        with console.status("[bold green]Executing tasks...[/bold green]") as status:
            last_status = None
            while True:
                await asyncio.sleep(0.5)
                snapshot: tuple[RunStatus, str | None, list[str]] | None
                if db_manager.db_url.startswith("sqlite+aiosqlite:///"):
                    try:
                        snapshot = await asyncio.to_thread(
                            _sqlite_monitor_snapshot,
                            db_manager.db_url,
                            run_id=run_id,
                            project_id=project_id,
                        )
                    except sqlite3.OperationalError:
                        # A busy SQLite read must not interfere with the
                        # scheduler writer; the next polling interval retries.
                        continue
                else:
                    async with UnitOfWork(db_manager, read_only=True) as uow:
                        assert uow.executions is not None
                        assert uow.tasks is not None
                        refreshed_run = await uow.executions.get_run(run_id)
                        if refreshed_run is None:
                            snapshot = None
                        else:
                            all_tasks = await uow.tasks.list_tasks_for_project(project_id)
                            snapshot = (
                                refreshed_run.status,
                                refreshed_run.summary,
                                [
                                    f"{t.key} ({t.status.value})"
                                    for t in all_tasks
                                    if t.status
                                    in (
                                        TaskStatus.CLAIMED,
                                        TaskStatus.PLANNING,
                                        TaskStatus.IMPLEMENTING,
                                        TaskStatus.TESTING,
                                        TaskStatus.REPAIRING,
                                    )
                                ],
                            )
                if snapshot is None:
                    break
                refreshed_status, refreshed_summary, running_tasks = snapshot

                # Print progress updates on status changes
                if refreshed_status != last_status:
                    console.print(
                        f"Run {run_id} status changed: "
                        f"[magenta]{refreshed_status.value}[/magenta]"
                    )
                    last_status = refreshed_status

                if refreshed_status in (
                    RunStatus.COMPLETED,
                    RunStatus.FAILED,
                    RunStatus.CANCELLED,
                    RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
                ):
                    if refreshed_status == RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW:
                        console.print(
                            "[bold yellow]Run ended in "
                            "BLOCKED_NEEDS_HUMAN_REVIEW.[/bold yellow]"
                        )
                        console.print(
                            "Some tasks could not be recovered within "
                            "the configured budget. Review run_summary.md "
                            "and resume them manually."
                        )
                    else:
                        console.print(
                            f"\n[bold green]Run finished with status: "
                            f"{refreshed_status.value}[/bold green]"
                        )
                    if refreshed_summary:
                        console.print(f"[bold]Summary:[/bold] {refreshed_summary}")
                    break

                if running_tasks:
                    status.update(
                        "[bold green]Executing tasks: "
                        f"{', '.join(running_tasks)}...[/bold green]"
                    )
                else:
                    status.update("[bold green]Scheduler waiting/idle...[/bold green]")

    try:
        await asyncio.wait_for(monitor_run(), timeout=monitor_timeout)
    except TimeoutError as e:
        async with UnitOfWork(db_manager) as uow:
            assert uow.executions is not None
            timed_out_run = await uow.executions.get_run(run_id)
            if timed_out_run and timed_out_run.status not in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            ):
                timed_out_run.status = RunStatus.FAILED
                timed_out_run.summary = f"Run monitor timed out after {monitor_timeout} seconds."
                timed_out_run.ended_at = datetime.now(UTC)
                await uow.executions.update_run(timed_out_run)
        raise RuntimeError(f"Run monitor timed out after {monitor_timeout} seconds.") from e
    finally:
        await scheduler.stop(timeout=2.0)


async def reconcile_interrupted_run(
    *, run_id: int | None = None, reason: str
) -> bool:
    """Reconcile a run whose worker was terminated outside the scheduler."""

    cwd = Path.cwd()
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.executions is not None
        assert uow.tasks is not None
        project = await uow.projects.get_project_by_path(str(cwd))
        if project is None or project.id is None:
            return False
        runs = await uow.executions.list_runs_for_project(project.id)
        candidates = [run for run in runs if run_id is None or run.id == run_id]
        if not candidates:
            return False
        target = max(candidates, key=lambda item: item.id or 0)
        terminal = {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
        }
        if target.status not in terminal:
            active_statuses = {
                TaskStatus.CLAIMED,
                TaskStatus.PLANNING,
                TaskStatus.IMPLEMENTING,
                TaskStatus.TESTING,
                TaskStatus.REPAIRING,
                TaskStatus.REVIEWING,
            }
            for task in await uow.tasks.list_tasks_for_project(project.id):
                if task.id is not None and task.status in active_statuses:
                    await uow.tasks.update_task_status(task.id, TaskStatus.FAILED_SAFE)
            for task_run in await uow.tasks.list_runs_for_run(target.id or -1):
                if task_run.status in {TaskRunStatus.PENDING, TaskRunStatus.RUNNING}:
                    task_run.status = TaskRunStatus.FAILED
                    task_run.ended_at = datetime.now(UTC)
                    task_run.final_summary = reason[:1200]
                    await uow.tasks.update_task_run(task_run)
            target.status = RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW
            target.ended_at = datetime.now(UTC)
            target.summary = (
                "Run reconciled after external worker interruption.\n"
                f"Reason: {reason[:1200]}"
            )
            await uow.executions.update_run(target)

    if project.id is not None:
        database_identity = getattr(db_manager, "db_url", "default")
        if ":memory:" in str(database_identity):
            database_identity = f"{database_identity}:instance:{id(db_manager)}"
        goal_id = goal_id_for_project(project.id, target.resource_limits)
        state_path = state_path_for_goal(cwd, goal_id, database_identity)
        if state_path.exists():
            ControlPlaneKernel(ControlPlaneStore(state_path)).abort(reason)
    console.print(
        f"[bold yellow]Reconciled interrupted Run {target.id} as "
        f"{target.status.value}.[/bold yellow]"
    )
    return True


def run_cmd(
    unattended: bool = typer.Option(
        False, "--unattended", help="Run in unattended mode without manual approvals."
    ),
    reconcile_interrupted: bool = typer.Option(
        False,
        "--reconcile-interrupted",
        help="Close the latest externally interrupted run and its control-plane lease.",
    ),
    run_id: int | None = typer.Option(
        None, "--run-id", help="Run ID to reconcile instead of the latest run."
    ),
    reason: str = typer.Option(
        "worker_process_interrupted",
        "--reason",
        help="Auditable reason persisted in the run and task receipts.",
    ),
) -> None:
    """Execute the pipeline loop for ready tasks in the current workspace."""
    try:
        if reconcile_interrupted:
            if not asyncio.run(reconcile_interrupted_run(run_id=run_id, reason=reason)):
                console.print("[bold red]No matching interrupted run found.[/bold red]")
                raise typer.Exit(code=1)
            return
        asyncio.run(run_execution(unattended))
    except typer.Exit as e:
        raise e
    except Exception as e:
        # Windows Rich output can fail while rendering a non-ASCII exception
        # on a legacy console code page. Preserve the diagnostic as ASCII
        # escapes so the original pipeline error remains visible.
        safe_error = str(e).encode("ascii", "backslashreplace").decode("ascii")
        console.print(
            f"[bold red]Run execution failed with unexpected error:[/bold red] {safe_error}"
        )
        raise typer.Exit(code=1) from e


def _run_resource_limits() -> dict[str, float | int]:
    try:
        budgets = load_config().budgets
    except Exception:
        return {}
    return {
        "max_task_duration": budgets.max_task_duration,
        "max_repair_attempts": budgets.max_repair_attempts,
        "max_file_count": budgets.max_file_count,
        "max_diff_growth": budgets.max_diff_growth,
        "max_active_model_calls": budgets.max_active_model_calls,
        "max_paid_calls": budgets.max_paid_calls,
        "max_paid_input_tokens": budgets.max_paid_input_tokens,
        "max_paid_output_tokens": budgets.max_paid_output_tokens,
        "max_paid_usd": budgets.max_paid_usd,
    }
