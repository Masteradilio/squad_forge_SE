import os
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Default to a local SQLite database file in .localforge directory
DEFAULT_DB_URL = "sqlite+aiosqlite:///.localforge/localforge.db"


def resolve_database_url() -> str:
    """Resolve an explicit URL or safely assemble one from DB components."""
    configured = os.getenv("LOCALFORGE_DATABASE_URL") or os.getenv("DATABASE_URL")
    if configured:
        return configured

    host = os.getenv("POSTGRES_HOST")
    if not host:
        return DEFAULT_DB_URL

    username = quote(os.getenv("POSTGRES_USER", "forgeos"), safe="")
    password = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    database = quote(os.getenv("POSTGRES_DB", "forgeos"), safe="")
    port = os.getenv("POSTGRES_PORT", "5432")
    credentials = f"{username}:{password}@" if password else f"{username}@"
    return f"postgresql+asyncpg://{credentials}{host}:{port}/{database}"


DATABASE_URL = resolve_database_url()


class DatabaseManager:
    """Manages the connection engine and session factory for the async database."""

    def __init__(self, db_url: str):
        self.db_url = db_url

        # Check if we are using SQLite and setup appropriate connection options
        is_sqlite = db_url.startswith("sqlite")
        connect_args: dict[str, object] = {}
        kwargs: dict[str, Any] = {}
        if is_sqlite:
            # check_same_thread=False is required for sqlite+aiosqlite in async mode
            connect_args["check_same_thread"] = False
            # OmniRoute visual retries can leave short-lived read/write
            # contention while the scheduler closes a failed task. Give
            # SQLite enough time to serialize that writer on Windows.
            connect_args["timeout"] = 120
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
            if ":memory:" in db_url:
                from sqlalchemy.pool import StaticPool

                kwargs["poolclass"] = StaticPool

        self.engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            connect_args=connect_args,
            **kwargs,
        )

        if is_sqlite:
            from sqlalchemy import event

            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
                cursor = dbapi_connection.cursor()
                try:
                    # journal_mode is a database-wide setting. Changing it on
                    # every pooled connection can deadlock a writer while a
                    # monitor session is opening during a scheduler commit.
                    cursor.execute("PRAGMA busy_timeout=120000")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                except Exception:
                    pass
                finally:
                    cursor.close()

        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get_session(self) -> AsyncSession:
        """Create a new AsyncSession."""
        return self.session_factory()

    async def close(self) -> None:
        """Dispose of the connection pool."""
        await self.engine.dispose()


# Global default database manager
db_manager = DatabaseManager(DATABASE_URL)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator for FastAPI or manual session retrieval."""
    session = await db_manager.get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
