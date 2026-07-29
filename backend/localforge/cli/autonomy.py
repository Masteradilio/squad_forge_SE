import asyncio
from typing import Any

import typer
from localforge.models.enums import AutonomyLevel
from localforge.storage import UnitOfWork, db_manager
from rich.console import Console

console = Console()
autonomy_app = typer.Typer(
    help="Manage and inspect Autonomy Policies and Maker/Checker Verifications."
)


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@autonomy_app.command("evaluate")
def evaluate_autonomy(
    level: str = typer.Option(
        "L1_INSPECT", "--level", "-l", help="L0_SIMULATE, L1_INSPECT, L2_ISOLATED, L3_UNATTENDED"
    ),
    action_kind: str = typer.Option(
        "write_file",
        "--action",
        "-a",
        help="write_file, run_command, git_commit, pr_ready, git_merge",
    ),
    target: str = typer.Option(None, "--target", "-t", help="Target path or command"),
) -> None:
    """Evaluate whether an action is permitted under an AutonomyLevel."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.autonomy is not None
            try:
                level_enum = AutonomyLevel(level.upper())
            except ValueError as exc:
                console.print(f"[bold red]Invalid AutonomyLevel: {level}[/bold red]")
                raise typer.Exit(1) from exc

            allowed, result_code, reason = uow.autonomy.evaluate_action(
                level=level_enum,
                action_kind=action_kind,
                target=target,
            )

            color = "green" if allowed else "red"
            console.print(f"[{color}]Allowed: {allowed}[/{color}]")
            console.print(f"Result Code: {result_code.value}")
            console.print(f"Reason: {reason}")

    _run_async(_impl())


@autonomy_app.command("verify-pr")
def verify_pr_ready(task_run_id: int = typer.Argument(..., help="TaskRun ID")) -> None:
    """Check if a task run has a valid independent Maker/Checker verification for PR_READY."""

    async def _impl() -> None:
        async with UnitOfWork(db_manager) as uow:
            assert uow.maker_checker is not None
            eligible, reason = await uow.maker_checker.verify_pr_ready_eligibility(task_run_id)

            if eligible:
                console.print(
                    f"[bold green]TaskRun {task_run_id} is ELIGIBLE for PR_READY: {reason}[/bold green]"
                )
            else:
                console.print(
                    f"[bold red]TaskRun {task_run_id} is INELIGIBLE for PR_READY: {reason}[/bold red]"
                )

    _run_async(_impl())


@autonomy_app.command("pre-pr-check")
def pre_pr_check(
    project_id: int = typer.Option(..., "--project-id", "-p", help="Project ID"),
    task_run_id: int = typer.Option(..., "--task-run-id", "-r", help="TaskRun ID"),
) -> None:
    """Run mechanical pre-PR gate checks (secret scanning, file count, verifier evidence)."""

    async def _impl() -> None:
        from localforge.safety.pre_pr_gate import MechanicalPrePRGate

        gate = MechanicalPrePRGate()
        async with UnitOfWork(db_manager) as uow:
            res = await gate.evaluate_gate(
                project_id=project_id,
                task_run_id=task_run_id,
                uow=uow,
            )

            if res.passed:
                console.print(
                    f"[bold green]Pre-PR Gate PASSED for TaskRun {task_run_id}[/bold green]"
                )
            else:
                console.print(f"[bold red]Pre-PR Gate FAILED for TaskRun {task_run_id}:[/bold red]")
                for v in res.violations:
                    console.print(f"  - [red]{v}[/red]")

    _run_async(_impl())
