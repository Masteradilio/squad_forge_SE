from types import SimpleNamespace

import pytest
from localforge.storage.bootstrap import (
    CURRENT_VERSION,
    bootstrap_database,
    get_table_columns,
)
from localforge.storage.database import DatabaseManager
from sqlalchemy import text


def test_bootstrap_import():
    import localforge

    assert localforge.__version__ == "6.2.0"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakePostgresConnection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.statements = []

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        return _FakeResult([("id",), ("tenant_id",)])


@pytest.mark.asyncio
async def test_get_table_columns_uses_sqlite_and_postgresql_introspection():
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    try:
        async with manager.engine.begin() as connection:
            await connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, tenant_id TEXT)"))
            assert await get_table_columns(connection, "projects") == {"id", "tenant_id"}
    finally:
        await manager.close()

    postgres_connection = _FakePostgresConnection()
    assert await get_table_columns(postgres_connection, "projects") == {"id", "tenant_id"}
    statement, params = postgres_connection.statements[0]
    assert "PRAGMA" not in statement.upper()
    assert "information_schema.columns" in statement
    assert params == {"table_name": "projects"}


@pytest.mark.asyncio
async def test_bootstrap_migrates_schema_v20_to_v22_with_tenant_and_approval_columns(tmp_path):
    db_path = tmp_path / "schema-v20.db"
    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        async with manager.engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE schema_versions (version INTEGER PRIMARY KEY, applied_at DATETIME)")
            )
            await connection.execute(text("INSERT INTO schema_versions(version) VALUES (20)"))
            await connection.execute(
                text("CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL)")
            )
            await connection.execute(text("INSERT INTO projects(id, name) VALUES (1, 'legacy project')"))
            await connection.execute(
                text("CREATE TABLE action_approvals (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL)")
            )

        assert await bootstrap_database(manager) == CURRENT_VERSION

        async with manager.engine.begin() as connection:
            project_columns = await get_table_columns(connection, "projects")
            approval_columns = await get_table_columns(connection, "action_approvals")
            task_run_columns = await get_table_columns(connection, "task_runs")
            assert "heartbeat_at" in task_run_columns
            assert "tenant_id" in project_columns
            assert {"expires_at", "decision_nonce", "decision_reason", "idempotency_key"}.issubset(
                approval_columns
            )
            tenant_id = await connection.scalar(text("SELECT tenant_id FROM projects WHERE id = 1"))
            assert tenant_id == "local"
            version = await connection.scalar(
                text("SELECT version FROM schema_versions ORDER BY version DESC LIMIT 1")
            )
            assert version == CURRENT_VERSION
            indexes = await connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'index' "
                    "AND name IN ('uq_action_approval_idempotency', 'ix_projects_tenant_id')"
                )
            )
            assert {str(row[0]) for row in indexes.fetchall()} == {
                "uq_action_approval_idempotency",
                "ix_projects_tenant_id",
            }

        assert await bootstrap_database(manager) == CURRENT_VERSION
    finally:
        await manager.close()
