"""Strict Package Version Locking — Generates package-lock.json / uv.lock to freeze dependencies."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PackageLocker:
    """Freezes dependency lockfiles immediately upon project initialization."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    def freeze_npm_lockfile(self) -> Path:
        """Ensure package-lock.json is created and locked."""
        lock_path = self.workspace_path / "package-lock.json"
        if lock_path.exists() or not (self.workspace_path / "package.json").exists():
            return lock_path

        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError("npm is required to create a reproducible package-lock.json")
        _run_lock_command(
            [npm, "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            self.workspace_path,
        )
        if not lock_path.exists():
            raise RuntimeError("npm completed without creating package-lock.json")
        json.loads(lock_path.read_text(encoding="utf-8"))
        logger.info("PackageLocker froze npm package-lock.json from package metadata.")
        return lock_path

    def freeze_python_lockfile(self) -> Path:
        """Ensure a pyproject workspace has a real uv lockfile."""
        lock_path = self.workspace_path / "uv.lock"
        if lock_path.exists() or not (self.workspace_path / "pyproject.toml").exists():
            return lock_path

        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("uv is required to create a reproducible uv.lock")
        _run_lock_command([uv, "lock"], self.workspace_path)
        if not lock_path.exists() or not lock_path.read_text(encoding="utf-8").strip():
            raise RuntimeError("uv completed without creating uv.lock")
        logger.info("PackageLocker froze uv.lock from pyproject metadata.")
        return lock_path

    def freeze_all(self) -> list[Path]:
        """Freeze every dependency manifest present in the workspace."""
        return [self.freeze_npm_lockfile(), self.freeze_python_lockfile()]


def _run_lock_command(command: list[str], cwd: Path) -> None:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"dependency lock command failed: {command[0]}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command returned a non-zero exit code").strip()
        raise RuntimeError(f"dependency lock command failed: {detail[-500:]}")
