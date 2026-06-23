import asyncio
import os
from datetime import UTC, datetime

import typer
from localforge.core.config import load_config
from localforge.models import domain
from localforge.models.enums import RunMode, RunStatus, TaskStatus
from localforge.services.scheduler import Scheduler
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console

console = Console()


async def run_execution(unattended: bool) -> None:
    cwd = os.getcwd()
    lf_dir = os.path.join(cwd, ".localforge")
    if not os.path.exists(lf_dir):
        console.print(
            "[bold red]Workspace not initialized. Run 'localforge init' first.[/bold red]"
        )
        raise typer.Exit(code=1)

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
            f"[bold green]Starting Run {run.id}[/bold green] "
            f"in [cyan]{mode.value}[/cyan] mode..."
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
                async with UnitOfWork(db_manager) as uow:
                    assert uow.executions is not None
                    assert uow.tasks is not None

                    refreshed_run = await uow.executions.get_run(run_id)
                    if not refreshed_run:
                        break

                    # Print progress updates on status changes
                    if refreshed_run.status != last_status:
                        console.print(
                            f"Run {run_id} status changed: "
                            f"[magenta]{refreshed_run.status.value}[/magenta]"
                        )
                        last_status = refreshed_run.status

                    if refreshed_run.status in (
                        RunStatus.COMPLETED,
                        RunStatus.FAILED,
                        RunStatus.CANCELLED,
                    ):
                        console.print(
                            f"\n[bold green]Run finished with status: "
                            f"{refreshed_run.status.value}[/bold green]"
                        )
                        if refreshed_run.summary:
                            console.print(f"[bold]Summary:[/bold] {refreshed_run.summary}")
                        break

                    # Display currently executing task runs
                    running_tasks = []
                    all_tasks = await uow.tasks.list_tasks_for_project(project_id)
                    for t in all_tasks:
                        if t.status in (
                            TaskStatus.CLAIMED,
                            TaskStatus.PLANNING,
                            TaskStatus.IMPLEMENTING,
                            TaskStatus.TESTING,
                            TaskStatus.REPAIRING,
                        ):
                            running_tasks.append(f"{t.key} ({t.status.value})")

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
                timed_out_run.summary = (
                    f"Run monitor timed out after {monitor_timeout} seconds."
                )
                timed_out_run.ended_at = datetime.now(UTC)
                await uow.executions.update_run(timed_out_run)
        raise RuntimeError(
            f"Run monitor timed out after {monitor_timeout} seconds."
        ) from e
    finally:
        await scheduler.stop(timeout=2.0)


def run_cmd(
    unattended: bool = typer.Option(
        False, "--unattended", help="Run in unattended mode without manual approvals."
    )
) -> None:
    """Execute the pipeline loop for ready tasks in the current workspace."""
    try:
        asyncio.run(run_execution(unattended))
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Run execution failed with unexpected error:[/bold red] {e}")
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
