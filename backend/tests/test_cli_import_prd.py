import asyncio
import json
import os

import localforge.cli.import_prd as import_mod
import localforge.storage.database as db_mod
from localforge.cli.main import app
from localforge.models import domain
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_import_prd_dry_run_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".localforge").mkdir()
    prd_path = tmp_path / "PRD.md"
    prd_path.write_text("# PRD\n\n## Importer\n- Load Markdown\n", encoding="utf-8")

    db_path = os.path.join(tmp_path, "lf.db").replace("\\", "/")
    db_url = f"sqlite+aiosqlite:///{db_path}"
    test_manager = db_mod.DatabaseManager(db_url)
    original_manager = db_mod.db_manager
    db_mod.db_manager = test_manager

    import_mod.db_manager = test_manager

    try:
        asyncio.run(bootstrap_database(test_manager))
        asyncio.run(seed_project(test_manager, tmp_path))
        result = runner.invoke(app, ["import-prd", str(prd_path), "--dry-run", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["persisted"] is False
        assert payload["tasks_created"] >= 1
    finally:
        asyncio.run(test_manager.close())
        db_mod.db_manager = original_manager
        import_mod.db_manager = original_manager


async def seed_project(test_manager: db_mod.DatabaseManager, tmp_path) -> None:
    async with UnitOfWork(test_manager) as uow:
        assert uow.projects is not None
        await uow.projects.create_project(
            domain.Project(name="CLI", root_path=str(tmp_path), default_branch="main")
        )
