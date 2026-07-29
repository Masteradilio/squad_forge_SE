import os

import localforge.storage.database as db_mod
from localforge.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_help():
    """Verify that --help command displays command options and instructions."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "LocalForge OS" in result.stdout
    assert "init" in result.stdout
    assert "doctor" in result.stdout
    assert "status" in result.stdout
    for command in [
        "pause",
        "resume",
        "stop",
        "tasks",
        "task",
        "logs",
        "replay",
        "models",
        "skills",
        "safety",
    ]:
        assert command in result.stdout


def test_cli_version_is_non_destructive_smoke_check():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "LocalForge OS 6.2.0"


def test_cli_doctor():
    """Verify that doctor command executes successfully."""
    result = runner.invoke(app, ["doctor"])
    # May exit with 0 or 1 depending on whether all system utilities (Docker/Git)
    # exist, but should always display the diagnostics table
    assert "Diagnostics" in result.stdout

    # Test JSON output
    result_json = runner.invoke(app, ["doctor", "--json"])
    assert "python" in result_json.stdout


def test_cli_init_and_status(tmp_path, monkeypatch):
    """Test init and status command cycle inside an isolated temp workspace."""
    # Move working directory to isolated temp path
    monkeypatch.chdir(tmp_path)

    # Set environment variable for test DB path with forward slashes
    # for Windows compatibility (3 slashes for absolute path)
    test_db_file = os.path.join(tmp_path, "test_localforge.db").replace("\\", "/")
    monkeypatch.setenv("LOCALFORGE_DATABASE_URL", f"sqlite+aiosqlite:///{test_db_file}")

    # Inject a new DatabaseManager to override the imported one
    test_manager = db_mod.DatabaseManager(f"sqlite+aiosqlite:///{test_db_file}")
    original_manager = db_mod.db_manager
    db_mod.db_manager = test_manager

    # Override namespaces of imported CLI modules to use the test manager
    import localforge.cli.init as init_mod
    import localforge.cli.status as status_mod

    init_mod.db_manager = test_manager
    status_mod.db_manager = test_manager

    try:
        # 1. Run status before init (should fail / say uninitialized)
        result_uninit = runner.invoke(app, ["status"])
        assert result_uninit.exit_code == 1
        assert "Workspace not initialized" in result_uninit.stdout

        # 2. Run init
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "successfully initialized" in result.stdout

        # Check directories and configuration file exist
        assert os.path.exists(os.path.join(tmp_path, ".localforge"))
        assert os.path.exists(os.path.join(tmp_path, ".localforge", "config.yaml"))
        assert os.path.exists(os.path.join(tmp_path, ".localforge", "policies", "default.yaml"))

        # 3. Run status after init
        result_status = runner.invoke(app, ["status"])
        assert result_status.exit_code == 0
        assert "Workspace Status" in result_status.stdout
        assert os.path.basename(tmp_path) in result_status.stdout

        # Test status JSON output
        result_status_json = runner.invoke(app, ["status", "--json"])
        assert result_status_json.exit_code == 0
        assert '"initialized": true' in result_status_json.stdout

    finally:
        import asyncio

        try:
            asyncio.run(db_mod.db_manager.close())
        except Exception:
            pass
        db_mod.db_manager = original_manager
        init_mod.db_manager = original_manager
        status_mod.db_manager = original_manager
