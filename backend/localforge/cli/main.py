import typer

from localforge import __version__
from localforge.cli.benchmark import benchmark_app
from localforge.cli.control import (
    chief_engineer_app,
    logs_cmd,
    models_app,
    pause_cmd,
    replay_cmd,
    resume_cmd,
    safety_app,
    skills_app,
    stop_cmd,
    task_app,
    tasks_app,
)
from localforge.cli.costs import costs_app
from localforge.cli.doctor import doctor_cmd
from localforge.cli.import_prd import import_prd_cmd
from localforge.cli.init import init_cmd
from localforge.cli.loops import loops_app
from localforge.cli.plan import plan_cmd

from localforge.cli.prs import prs_cmd
from localforge.cli.run import run_cmd
from localforge.cli.squad import squad_app
from localforge.cli.status import status_cmd


app = typer.Typer(
    name="localforge",
    help="LocalForge OS — economy-aware software engineering control plane.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"LocalForge OS {__version__}")
        raise typer.Exit()


@app.callback()
def root_options(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed LocalForge version and exit.",
    ),
) -> None:
    """Global LocalForge CLI options."""
    del version


app.command(name="init", help="Initialize a LocalForge workspace in the current directory.")(
    init_cmd
)
app.command(name="doctor", help="Run system diagnostics and verify dependencies.")(doctor_cmd)
app.command(name="import-prd", help="Import a Markdown PRD into draft epics and tasks.")(
    import_prd_cmd
)
app.command(name="status", help="Display project, task, and daemon status summary.")(status_cmd)
app.command(name="plan", help="Manage backlog planning and approve task implementation plans.")(
    plan_cmd
)
app.command(name="run", help="Execute the pipeline loop for ready tasks in the current workspace.")(
    run_cmd
)
app.command(name="prs", help="List local pull-request artifacts and their paths.")(prs_cmd)
app.command(name="pause", help="Pause the latest run in the current workspace.")(pause_cmd)
app.command(name="resume", help="Resume the latest paused run.")(resume_cmd)
app.command(name="stop", help="Stop the latest run safely.")(stop_cmd)
app.command(name="logs", help="Print recent audit log entries.")(logs_cmd)
app.command(name="replay", help="Export a replay timeline for a run.")(replay_cmd)
app.add_typer(tasks_app, name="tasks")
app.add_typer(task_app, name="task")
app.add_typer(models_app, name="models")
app.add_typer(chief_engineer_app, name="chief-engineer")
app.add_typer(skills_app, name="skills")
app.add_typer(safety_app, name="safety")
app.add_typer(costs_app, name="costs")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(squad_app, name="squad")
app.add_typer(loops_app, name="loops")



if __name__ == "__main__":
    app()
