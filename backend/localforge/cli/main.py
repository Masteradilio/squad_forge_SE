import typer
from localforge.cli.doctor import doctor_cmd
from localforge.cli.init import init_cmd
from localforge.cli.status import status_cmd

app = typer.Typer(
    name="localforge",
    help="LocalForge OS — Local-first autonomous software engineering operating system CLI.",
    no_args_is_help=True,
)

# Register subcommands directly
app.command(name="init", help="Initialize a new LocalForge workspace in the current directory.")(
    init_cmd
)
app.command(name="doctor", help="Run system diagnostics and verify dependencies.")(doctor_cmd)
app.command(name="status", help="Display project, task, and daemon status summary.")(status_cmd)


if __name__ == "__main__":
    app()
