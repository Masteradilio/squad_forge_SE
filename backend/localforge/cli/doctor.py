import asyncio
import json
import os
import shutil
import sys
import tempfile
from typing import Any

import typer
from localforge.core.config import load_config
from localforge.llm import LLMError, OpenAICompatibleProvider
from localforge.storage import db_manager, get_current_schema_version
from rich.console import Console
from rich.table import Table

console = Console()


async def check_python() -> tuple[str, str, str]:
    """Check if Python version is >= 3.12 as specified in PRD."""
    v_major, v_minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{v_major}.{v_minor}.{sys.version_info.micro}"
    if v_major == 3 and v_minor >= 12:
        return "PASS", f"Python version {version_str} is compatible.", version_str
    elif v_major == 3 and v_minor == 11:
        return (
            "WARN",
            f"Python {version_str} detected. PRD recommends 3.12, but 3.11 is supported.",
            version_str,
        )
    else:
        return (
            "FAIL",
            f"Python version {version_str} is incompatible (Requires >= 3.11, recommended 3.12).",
            version_str,
        )


async def check_git() -> tuple[str, str, str]:
    """Check if Git CLI is installed and accessible."""
    git_path = shutil.which("git")
    if not git_path:
        return "FAIL", "Git CLI is not installed or not in PATH.", ""

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        version_str = stdout.decode().strip()
        return "PASS", f"Git detected: {version_str}", version_str
    except Exception as e:
        return "FAIL", f"Failed to execute Git command: {e}", ""


async def check_write_permissions() -> tuple[str, str, str]:
    """Check write permissions in the current working directory."""
    cwd = os.getcwd()
    try:
        with tempfile.TemporaryFile(dir=cwd) as f:
            f.write(b"test")
        return "PASS", "Write permissions verified in the current directory.", cwd
    except Exception as e:
        return "FAIL", f"Write permissions check failed in current directory: {e}", cwd


async def check_sqlite() -> tuple[str, str, str]:
    """Check connectivity to the SQLite database and retrieve schema version."""
    try:
        async with await db_manager.get_session() as session:
            version = await get_current_schema_version(session)
        return "PASS", f"SQLite connection succeeded. DB Schema version: {version}.", str(version)
    except Exception as e:
        return "FAIL", f"SQLite database connectivity check failed: {e}", ""


async def check_docker() -> tuple[str, str, str]:
    """Check if Docker is installed, running and Python SDK is functional."""
    # First check Python SDK
    sdk_installed = False
    docker_module: Any = None
    try:
        import docker as docker_sdk

        docker_module = docker_sdk
        sdk_installed = True
    except ImportError:
        pass

    docker_path = shutil.which("docker")
    if not docker_path:
        return (
            "WARN",
            "Docker is not installed. Containerized sandboxing will be unavailable.",
            "not_installed",
        )

    # Check daemon status
    daemon_running = False
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=3.0)
            daemon_running = proc.returncode == 0
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return (
                "WARN",
                "Docker command timed out checking daemon. Is it running?",
                "timeout",
            )
    except Exception as e:
        return "WARN", f"Failed to execute Docker check: {e}", "error"

    if daemon_running:
        if sdk_installed:
            try:
                # Verify SDK can connect
                client = docker_module.from_env()
                await asyncio.get_running_loop().run_in_executor(None, client.ping)
                return (
                    "PASS",
                    "Docker daemon is running and Python SDK is functional.",
                    "active",
                )
            except Exception as e:
                return (
                    "WARN",
                    f"Docker daemon is running, but Python SDK connection failed: {e}",
                    "sdk_connection_error",
                )
        else:
            return (
                "WARN",
                "Docker daemon is running, but Python 'docker' SDK is missing.",
                "missing_sdk",
            )
    else:
        return (
            "WARN",
            "Docker command exists, but daemon is not running.",
            "inactive",
        )


async def check_omniroute() -> tuple[str, str, str]:
    """Check that the configured OmniRoute gateway and route are available."""
    try:
        config = load_config()
    except Exception as e:
        return "WARN", f"Could not load local configuration: {e}", ""

    provider_url = config.models.base_url
    default_model = config.models.default_model

    try:
        provider = OpenAICompatibleProvider(
            base_url=provider_url,
            api_key=config.models.api_key,
            default_model=default_model,
            provider_name=config.models.provider,
        )
        available_models = await provider.list_models()
        if default_model in available_models:
            return (
                "PASS",
                f"LLM provider reachable at {provider_url}. Model '{default_model}' is available.",
                default_model,
            )
        else:
            models_str = ", ".join(available_models) if available_models else "None"
            return (
                "WARN",
                f"LLM provider reachable at {provider_url}, but default model "
                f"'{default_model}' was not found. Available models: {models_str}.",
                "",
            )
    except LLMError as e:
        return "WARN", f"LLM provider check failed at {provider_url}: {e}", ""
    except Exception as e:
        return "WARN", f"Unexpected error checking LLM provider at {provider_url}: {e}", ""


async def run_doctor(json_output: bool) -> None:
    """Execute all system diagnosis checks and display results."""
    checks = {
        "python": check_python(),
        "git": check_git(),
        "write_perms": check_write_permissions(),
        "sqlite": check_sqlite(),
        "docker": check_docker(),
        "omniroute": check_omniroute(),
    }

    results = {}
    has_failed = False

    # Execute all checks concurrently
    names = list(checks.keys())
    tasks = list(checks.values())
    completed = await asyncio.gather(*tasks)

    for name, (status, msg, details) in zip(names, completed, strict=True):
        results[name] = {
            "status": status,
            "message": msg,
            "details": details,
        }
        if status == "FAIL":
            has_failed = True

    if json_output:
        # Machine-readable JSON output
        sys.stdout.write(json.dumps(results, indent=2))
        sys.stdout.flush()
        if has_failed:
            raise typer.Exit(code=1)
        return

    # Premium human-readable CLI table output
    table = Table(
        title="LocalForge OS Diagnostics Report", show_header=True, header_style="bold magenta"
    )
    table.add_column("Component", style="cyan", width=15)
    table.add_column("Status", width=10)
    table.add_column("Details", style="green")

    for comp, data in results.items():
        status = data["status"]
        if status == "PASS":
            status_formatted = "[bold green]PASS[/bold green]"
        elif status == "WARN":
            status_formatted = "[bold yellow]WARN[/bold yellow]"
        else:
            status_formatted = "[bold red]FAIL[/bold red]"

        table.add_row(comp.capitalize(), status_formatted, data["message"])

    console.print(table)

    if has_failed:
        console.print(
            "\n[bold red]✖ LocalForge Doctor detected critical check failures. "
            "Please fix them to run properly.[/bold red]"
        )
        raise typer.Exit(code=1)
    else:
        console.print(
            "\n[bold green]✔ LocalForge Doctor completed successfully. "
            "Everything looks ready![/bold green]"
        )


def doctor_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Output diagnostic results in machine-readable JSON format."
    ),
) -> None:
    """Run system diagnostics and verify dependencies."""
    try:
        asyncio.run(run_doctor(json_output))
    except typer.Exit as e:
        raise e
    except Exception as e:
        console.print(f"[bold red]Doctor execution failed with unexpected error:[/bold red] {e}")
        raise typer.Exit(code=1) from e
