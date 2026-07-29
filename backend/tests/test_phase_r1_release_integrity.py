import asyncio
import json
import shutil
import sqlite3
import subprocess
import sys
import venv
from pathlib import Path

import pytest
from localforge.storage.bootstrap import (
    CURRENT_VERSION,
    UnsupportedSchemaVersionError,
    backup_sqlite_database,
    bootstrap_database,
    restore_sqlite_database,
)
from localforge.storage.database import DatabaseManager
from sqlalchemy import text


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_version_consistency_script_accepts_repository_state() -> None:
    result = _run([sys.executable, "scripts/check_version_consistency.py"])

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["version"] == "6.2.0"
    assert payload["release_tag"] == "v6.2.0"


def test_public_import_matrix_runs_in_clean_interpreter() -> None:
    result = _run([sys.executable, "scripts/check_import_matrix.py"])

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["failed"] == []
    assert "localforge.services.compliance_evidence" in payload["imported"]


def test_wheel_install_cli_and_import_smoke_without_pythonpath(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    result = _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheelhouse)])
    assert result.returncode == 0, result.stderr or result.stdout

    wheels = sorted(wheelhouse.glob("localforge_os-6.2.0-*.whl"))
    assert len(wheels) == 1

    venv_dir = tmp_path / "install-env"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(venv_dir)
    python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    install = _run([str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])])
    assert install.returncode == 0, install.stderr or install.stdout

    smoke = _run(
        [
            str(python),
            "-c",
            "import os; os.environ.pop('PYTHONPATH', None); import localforge; print(localforge.__version__)",
        ]
    )
    assert smoke.returncode == 0, smoke.stderr or smoke.stdout
    assert smoke.stdout.strip() == "6.2.0"

    cli = _run([str(python), "-m", "localforge.cli.main", "--version"])
    assert cli.returncode == 0, cli.stderr or cli.stdout
    assert cli.stdout.strip() == "LocalForge OS 6.2.0"


def test_sqlite_backup_restore_and_v5_fixture_upgrade_preserves_projects(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v5.db"
    restored_path = tmp_path / "restored.db"

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_versions (version INTEGER PRIMARY KEY, applied_at DATETIME);
            INSERT INTO schema_versions(version) VALUES (5);
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                root_path VARCHAR(1024) NOT NULL,
                default_branch VARCHAR(100) NOT NULL,
                remote_url VARCHAR(1024),
                localforge_config_path VARCHAR(1024),
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO projects(name, root_path, default_branch, remote_url)
            VALUES ('legacy project', '/tmp/legacy', 'main', 'git@example.com:repo.git');
            """
        )

    backup_path = backup_sqlite_database(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        backup_dir=tmp_path / "backups",
    )
    assert backup_path.exists()
    restore_sqlite_database(backup_path, restored_path)
    assert restored_path.exists()

    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        assert asyncio.run(bootstrap_database(manager)) == CURRENT_VERSION

        async def inspect() -> tuple[int, str]:
            async with await manager.get_session() as session:
                version = await session.scalar(
                    text("SELECT version FROM schema_versions ORDER BY version DESC LIMIT 1")
                )
                name = await session.scalar(text("SELECT name FROM projects WHERE id = 1"))
                return int(version), str(name)

        version, name = asyncio.run(inspect())
        assert version == CURRENT_VERSION
        assert name == "legacy project"
    finally:
        asyncio.run(manager.close())


def test_future_schema_version_fails_safely(tmp_path: Path) -> None:
    db_path = tmp_path / "future.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_versions(version) VALUES (?)", (CURRENT_VERSION + 1,))

    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        with pytest.raises(UnsupportedSchemaVersionError):
            asyncio.run(bootstrap_database(manager))
    finally:
        asyncio.run(manager.close())


def teardown_module() -> None:
    shutil.rmtree("build", ignore_errors=True)
