import logging
import os

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.storage.database import DatabaseManager
from localforge.storage.orm import Base, SchemaVersionORM

logger = logging.getLogger(__name__)

CURRENT_VERSION = 1


async def ensure_db_directory(db_url: str) -> None:
    """Ensure that the parent directory for a SQLite database file exists."""
    if db_url.startswith("sqlite+aiosqlite:///"):
        # Extract the filepath after the protocol
        db_path = db_url[len("sqlite+aiosqlite:///") :]
        # Handle Windows absolute paths with drive letters (e.g. /C:/path)
        if db_path.startswith("/") and len(db_path) > 2 and db_path[2] == ":":
            db_path = db_path[1:]

        if db_path and db_path != ":memory:":
            # Normalize path
            db_path = os.path.abspath(db_path)
            dir_path = os.path.dirname(db_path)
            if dir_path and not os.path.exists(dir_path):
                logger.info(f"Creating database directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)


async def get_current_schema_version(session: AsyncSession) -> int:
    """Retrieve the current schema version from the database.

    Returns 0 if the schema_versions table does not exist.
    """
    try:
        # Check if the schema_versions table exists by querying it
        result = await session.execute(
            text("SELECT version FROM schema_versions ORDER BY version DESC LIMIT 1")
        )
        row = result.fetchone()
        if row:
            return int(row[0])
        return 0
    except OperationalError:
        # Table likely does not exist
        return 0


async def bootstrap_database(db_manager: DatabaseManager) -> int:
    """Initialize the database schema and apply migrations.

    Returns the applied schema version.
    """
    await ensure_db_directory(db_manager.db_url)

    async with await db_manager.get_session() as session:
        current_version = await get_current_schema_version(session)
        logger.info(f"Current database schema version: {current_version}")

        if current_version == 0:
            logger.info("Initializing new database schema (Version 1)...")
            # In SQLAlchemy async, we run create_all on the sync connection within a run_sync block
            async with db_manager.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Record version 1 application
            version_record = SchemaVersionORM(version=1)
            session.add(version_record)
            await session.commit()
            logger.info("Database schema initialized successfully.")
            return 1

        elif current_version < CURRENT_VERSION:
            # Here we would handle incremental migrations if CURRENT_VERSION was > 1.
            # e.g., if current_version == 1: run_migration_to_2(session)
            logger.info(
                f"Migrating database from version {current_version} to {CURRENT_VERSION}..."
            )
            # For now, version 1 is the latest, so we do nothing.
            return current_version

        else:
            logger.info("Database is already up to date.")
            return current_version
