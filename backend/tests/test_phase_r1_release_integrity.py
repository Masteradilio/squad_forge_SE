import asyncio
import json
import shutil
import sqlite3
import subprocess
import sys
import venv
import zipfile
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

import scripts.check_clean_package_install as package_smoke


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


def test_candidate_evidence_check_script_accepts_committed_manifests() -> None:
    result = _run([sys.executable, "scripts/check_candidate_evidence.py"])

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["manifest_count"] >= 12


def test_package_smoke_script_reports_failed_build(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fake_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
        encoding: str = "utf-8",
        errors: str = "replace",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, "", "build failed")

    monkeypatch.setattr(package_smoke.subprocess, "run", fake_run)

    assert package_smoke.main([]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    assert payload["commands"][0]["exit_code"] == 2


def test_package_smoke_script_discovers_single_sdist_and_wheel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist_dir_holder: dict[str, Path] = {}

    class FakeTemporaryDirectory:
        def __init__(self, prefix: str) -> None:
            self.path = tmp_path / prefix.rstrip("-")

        def __enter__(self) -> str:
            self.path.mkdir(parents=True, exist_ok=True)
            return str(self.path)

        def __exit__(self, *args: object) -> None:
            return None

    def fake_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
        encoding: str = "utf-8",
        errors: str = "replace",
    ) -> subprocess.CompletedProcess[str]:
        if "-m" in command and "build" in command:
            outdir = Path(command[command.index("--outdir") + 1])
            dist_dir_holder["path"] = outdir
            outdir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(outdir / "localforge_os-6.2.0-py3-none-any.whl", "w") as wheel_archive:
                wheel_archive.writestr("localforge/__init__.py", "")
            (outdir / "localforge_os-6.2.0.tar.gz").write_text("sdist", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    class FakeEnvBuilder:
        def __init__(self, *, with_pip: bool, system_site_packages: bool) -> None:
            self.with_pip = with_pip
            self.system_site_packages = system_site_packages

        def create(self, venv_dir: Path) -> None:
            scripts_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
            scripts_dir.mkdir(parents=True, exist_ok=True)
            (scripts_dir / ("python.exe" if sys.platform == "win32" else "python")).write_text("", encoding="utf-8")

    monkeypatch.setattr(package_smoke.tempfile, "TemporaryDirectory", FakeTemporaryDirectory)
    monkeypatch.setattr(package_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(package_smoke.venv, "EnvBuilder", FakeEnvBuilder)
    monkeypatch.setattr(package_smoke.shutil, "rmtree", lambda *args, **kwargs: None)

    assert package_smoke.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["artifacts"] == [
        "localforge_os-6.2.0-py3-none-any.whl",
        "localforge_os-6.2.0.tar.gz",
    ]
    assert dist_dir_holder["path"].name == "dist"


def test_wheel_install_cli_and_import_smoke_without_pythonpath(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    result = _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheelhouse)])
    assert result.returncode == 0, result.stderr or result.stdout

    wheels = sorted(wheelhouse.glob("localforge_os-6.2.0-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel_archive:
        assert not any(name.startswith("tests/") for name in wheel_archive.namelist())

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
