from pathlib import Path

import typer
from localforge.demo import run_ci_regression_demo

DEFAULT_DEMO_OUTPUT = Path("docs/e2e/v6_2_compliance/phase_R11/demo")
DEMO_OUTPUT_OPTION = typer.Option(DEFAULT_DEMO_OUTPUT, "--output")


def demo_cmd(
    scenario: str = typer.Option("ci-regression", "--scenario"),
    deterministic: bool = typer.Option(False, "--deterministic"),
    output: Path = DEMO_OUTPUT_OPTION,
) -> None:
    """Run a deterministic CPU-only demo scenario and export replay evidence."""
    if scenario != "ci-regression":
        raise typer.BadParameter("Only --scenario ci-regression is supported.")
    if not deterministic:
        raise typer.BadParameter("Use --deterministic for the CPU-only replay demo.")

    demo = run_ci_regression_demo(output)
    typer.echo(f"Demo status: {demo.status}")
    typer.echo(f"Evidence: {output / 'demo_run.json'}")
    typer.echo(f"Replay: {output / 'demo_replay.html'}")
