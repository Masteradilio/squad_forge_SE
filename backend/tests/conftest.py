from collections.abc import AsyncGenerator

import pytest_asyncio
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def db_manager():
    """Fixture providing an isolated DatabaseManager backed by an in-memory SQLite DB."""
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    # Bootstrap the tables
    await bootstrap_database(manager)
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def db_session(db_manager) -> AsyncGenerator[AsyncSession, None]:
    """Fixture providing a transactional AsyncSession for each test."""
    async with await db_manager.get_session() as session:
        yield session
        # Session rollback is implicitly handled on exit/failure by SQLAlchemy,
        # but since we are testing CRUD we want to ensure transactions clean up.
        await session.rollback()
