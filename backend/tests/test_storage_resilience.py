import sqlite3

import pytest
from localforge.storage.database import is_sqlite_lock_error, retry_sqlite_operation


@pytest.mark.anyio
async def test_retry_sqlite_operation_reopens_after_transient_lock():
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        return "heartbeat persisted"

    result = await retry_sqlite_operation(operation, db_url="sqlite+aiosqlite:///forge.db")

    assert result == "heartbeat persisted"
    assert attempts == 3


def test_sqlite_lock_classifier_does_not_hide_non_sqlite_failures():
    assert is_sqlite_lock_error(sqlite3.OperationalError("database is locked"), "sqlite:///x")
    assert not is_sqlite_lock_error(sqlite3.OperationalError("database is locked"), "postgresql://x")
    assert not is_sqlite_lock_error(ValueError("invalid task state"), "sqlite:///x")
