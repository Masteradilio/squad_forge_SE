import asyncio
import os
import shutil
import subprocess
from typing import Any

from localforge.runtime.process_tree import ProcessTreeController
from localforge.safety.command_validator import command_to_argv
from localforge.sandbox.base import BaseSandbox


class LocalSandbox(BaseSandbox):
    """Restricted local execution sandbox operating directly inside a task's worktree path."""

    def __init__(self, worktree_path: str):
        self.worktree_path = worktree_path
        self._status = "stopped"
        self.process_tree = ProcessTreeController()

    async def create(self) -> None:
        """Provision local worktree directory checks."""
        if not os.path.exists(self.worktree_path):
            raise FileNotFoundError(f"Worktree path '{self.worktree_path}' does not exist.")
        self._status = "running"

    async def execute(self, cmd: str, timeout: float = 60.0) -> tuple[int, str, str]:
        """Execute command local inside the worktree path."""
        if self._status != "running":
            raise RuntimeError("Sandbox is not running.")

        argv = command_to_argv(cmd)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        child_env = os.environ.copy()
        # Generated Python tests and source files are UTF-8. Keep local
        # sandbox subprocesses deterministic on Windows, where the ambient
        # code page is otherwise commonly cp1252.
        child_env.setdefault("PYTHONUTF8", "1")
        child_env.setdefault("PYTHONIOENCODING", "utf-8")
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.worktree_path,
            env=child_env,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
        self.process_tree.attach(proc)

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as e:
            await self._terminate_process(proc)
            raise TimeoutError(f"Command execution timed out after {timeout} seconds.") from e
        except asyncio.CancelledError:
            await self._terminate_process(proc)
            raise

        stdout_str = stdout_bytes.decode(errors="replace")
        stderr_str = stderr_bytes.decode(errors="replace")
        exit_code = proc.returncode if proc.returncode is not None else -1
        return exit_code, stdout_str, stderr_str

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        await self.process_tree.terminate(proc, "timeout_or_cancel")
        try:
            await asyncio.wait_for(asyncio.shield(proc.communicate()), timeout=5.0)
        except (TimeoutError, ProcessLookupError, ValueError):
            pass

    def process_tree_evidence(self) -> dict[str, Any] | None:
        evidence = self.process_tree.evidence
        return evidence.as_dict() if evidence else None

    async def copy_to(self, host_path: str, container_path: str) -> None:
        """Copy files locally if paths differ."""
        self._require_workspace_path(container_path, "write")
        if os.path.abspath(host_path) == os.path.abspath(container_path):
            return
        if os.path.isdir(host_path):
            if os.path.exists(container_path):
                shutil.rmtree(container_path)
            shutil.copytree(host_path, container_path)
        else:
            os.makedirs(os.path.dirname(container_path), exist_ok=True)
            shutil.copy2(host_path, container_path)

    async def copy_from(self, container_path: str, host_path: str) -> None:
        """Copy files locally if paths differ."""
        self._require_workspace_path(container_path, "read")
        if os.path.abspath(container_path) == os.path.abspath(host_path):
            return
        if os.path.isdir(container_path):
            if os.path.exists(host_path):
                shutil.rmtree(host_path)
            shutil.copytree(container_path, host_path)
        else:
            os.makedirs(os.path.dirname(host_path), exist_ok=True)
            shutil.copy2(container_path, host_path)

    def _require_workspace_path(self, path: str, operation: str) -> None:
        worktree = os.path.realpath(os.path.abspath(self.worktree_path))
        target = os.path.realpath(os.path.abspath(path))
        try:
            is_within_worktree = os.path.commonpath([worktree, target]) == worktree
        except ValueError:
            is_within_worktree = False
        if not is_within_worktree:
            raise PermissionError(f"Local sandbox cannot {operation} outside its worktree: {path}")

    async def destroy(self) -> None:
        """Halt local execution state."""
        self._status = "destroyed"

    async def status(self) -> str:
        """Query state status."""
        return self._status
