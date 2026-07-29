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


def test_sqlite_backup_restore_and_v5_fixture_upgrade_preserves_legacy_entities(
    tmp_path: Path,
) -> None:
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
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                epic_id INTEGER,
                key VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                acceptance_criteria JSON NOT NULL DEFAULT '[]',
                dependency_task_ids JSON NOT NULL DEFAULT '[]',
                risk_level VARCHAR(20) NOT NULL DEFAULT 'low',
                status VARCHAR(50) NOT NULL DEFAULT 'BACKLOG',
                assigned_agent_id INTEGER,
                metadata_json JSON NOT NULL DEFAULT '{}',
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO tasks(project_id, key, title, description, status)
            VALUES (1, 'LF-LEGACY-1', 'legacy task', 'legacy description', 'BACKLOG');
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                mode VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                started_at DATETIME,
                ended_at DATETIME,
                initiated_by VARCHAR(100) NOT NULL,
                resource_limits JSON NOT NULL DEFAULT '{}',
                summary TEXT
            );
            INSERT INTO runs(project_id, mode, status, initiated_by)
            VALUES (1, 'unattended', 'RUNNING', 'legacy');
            CREATE TABLE task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                worktree_path VARCHAR(1024),
                branch_name VARCHAR(255),
                sandbox_id VARCHAR(100),
                attempt_count INTEGER DEFAULT 1,
                started_at DATETIME,
                ended_at DATETIME,
                final_summary TEXT
            );
            INSERT INTO task_runs(run_id, task_id, status, branch_name)
            VALUES (1, 1, 'RUNNING', 'legacy/branch');
            CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_run_id INTEGER NOT NULL,
                type VARCHAR(50) NOT NULL,
                path VARCHAR(1024) NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                summary TEXT,
                created_at DATETIME
            );
            INSERT INTO artifacts(task_run_id, type, path, content_hash, summary)
            VALUES (1, 'PlanArtifact', 'artifacts/legacy-plan.md', 'abc123', 'legacy artifact');
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                run_id INTEGER,
                task_id INTEGER,
                actor_type VARCHAR(50) NOT NULL,
                actor_id VARCHAR(100),
                event_type VARCHAR(50) NOT NULL,
                payload_redacted JSON NOT NULL DEFAULT '{}',
                created_at DATETIME
            );
            INSERT INTO audit_events(project_id, run_id, task_id, actor_type, actor_id, event_type)
            VALUES (1, 1, 1, 'system', 'legacy-runner', 'task.started');
            CREATE TABLE memory_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                kind VARCHAR(50) NOT NULL DEFAULT 'stack_fact',
                fact TEXT NOT NULL,
                source VARCHAR(100) NOT NULL DEFAULT 'manual',
                pinned BOOLEAN NOT NULL DEFAULT 0,
                status VARCHAR(30) NOT NULL DEFAULT 'active',
                tags JSON NOT NULL DEFAULT '[]',
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO memory_facts(project_id, kind, fact, source, tags)
            VALUES (1, 'stack_fact', 'legacy memory', 'legacy', '["migration"]');
            CREATE TABLE swarm_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                task_run_id INTEGER NOT NULL,
                strategy VARCHAR(50) NOT NULL DEFAULT 'LIGHT',
                status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
                policy_json JSON NOT NULL DEFAULT '{}',
                nodes_json JSON NOT NULL DEFAULT '[]',
                edges_json JSON NOT NULL DEFAULT '[]',
                paused_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO swarm_plans(project_id, task_run_id, strategy, status)
            VALUES (1, 1, 'LIGHT', 'DRAFT');
            CREATE TABLE graph_mutation_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                graph_version INTEGER NOT NULL,
                parent_graph_version INTEGER NOT NULL,
                mutation_type VARCHAR(50) NOT NULL,
                actor_agent_id VARCHAR(255) NOT NULL,
                reason TEXT NOT NULL,
                payload_json JSON NOT NULL DEFAULT '{}',
                content_hash VARCHAR(64) NOT NULL,
                created_at DATETIME
            );
            INSERT INTO graph_mutation_journal(
                plan_id, graph_version, parent_graph_version, mutation_type,
                actor_agent_id, reason, content_hash
            )
            VALUES (1, 1, 0, 'ADD_NODE', 'legacy-agent', 'legacy mutation', 'def456');
            CREATE TABLE path_leases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                task_run_id INTEGER NOT NULL,
                owner_id VARCHAR(255) NOT NULL,
                target_path TEXT NOT NULL,
                is_directory BOOLEAN NOT NULL DEFAULT 0,
                ttl_seconds INTEGER NOT NULL DEFAULT 3600,
                expires_at DATETIME NOT NULL,
                release_reason VARCHAR(50),
                created_at DATETIME
            );
            INSERT INTO path_leases(project_id, task_run_id, owner_id, target_path, expires_at)
            VALUES (1, 1, 'legacy-owner', 'app/legacy.py', '2030-01-01T00:00:00');
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

        async def inspect() -> tuple[int, dict[str, int | str]]:
            async with await manager.get_session() as session:
                version = await session.scalar(
                    text("SELECT version FROM schema_versions ORDER BY version DESC LIMIT 1")
                )
                values: dict[str, int | str] = {
                    "project_name": str(
                        await session.scalar(text("SELECT name FROM projects WHERE id = 1"))
                    ),
                    "task_key": str(await session.scalar(text("SELECT key FROM tasks WHERE id = 1"))),
                    "run_count": int(
                        await session.scalar(text("SELECT COUNT(*) FROM runs")) or 0
                    ),
                    "task_run_count": int(
                        await session.scalar(text("SELECT COUNT(*) FROM task_runs")) or 0
                    ),
                    "artifact_count": int(
                        await session.scalar(text("SELECT COUNT(*) FROM artifacts")) or 0
                    ),
                    "audit_count": int(
                        await session.scalar(text("SELECT COUNT(*) FROM audit_events")) or 0
                    ),
                    "memory_count": int(
                        await session.scalar(text("SELECT COUNT(*) FROM memory_facts")) or 0
                    ),
                    "graph_count": int(
                        await session.scalar(
                            text("SELECT COUNT(*) FROM graph_mutation_journal")
                        )
                        or 0
                    ),
                    "lease_count": int(
                        await session.scalar(text("SELECT COUNT(*) FROM path_leases")) or 0
                    ),
                    "lease_token": str(
                        await session.scalar(
                            text("SELECT fencing_token FROM path_leases WHERE id = 1")
                        )
                    ),
                    "graph_sequence": int(
                        await session.scalar(
                            text(
                                "SELECT mutation_sequence FROM graph_mutation_journal "
                                "WHERE id = 1"
                            )
                        )
                        or 0
                    ),
                }
                return int(version), values

        version, values = asyncio.run(inspect())
        assert version == CURRENT_VERSION
        assert values == {
            "project_name": "legacy project",
            "task_key": "LF-LEGACY-1",
            "run_count": 1,
            "task_run_count": 1,
            "artifact_count": 1,
            "audit_count": 1,
            "memory_count": 1,
            "graph_count": 1,
            "lease_count": 1,
            "lease_token": "legacy-path-lease-1",
            "graph_sequence": 1,
        }
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
