import logging
import os
import tempfile

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.storage.database import DatabaseManager
from localforge.storage.orm import Base, SchemaVersionORM

logger = logging.getLogger(__name__)

CURRENT_VERSION = 9




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
    # Safety check for test environments to prevent writes/deadlocks on the real development DB
    if "PYTEST_CURRENT_TEST" in os.environ:
        db_url = db_manager.db_url
        if db_url.startswith("sqlite+aiosqlite:///"):
            db_path = db_url[len("sqlite+aiosqlite:///") :]
            if db_path.startswith("/") and len(db_path) > 2 and db_path[2] == ":":
                db_path = db_path[1:]

            if db_path != ":memory:":
                abs_db_path = os.path.abspath(db_path)
                normalized_abs = abs_db_path.lower().replace("\\", "/")

                # Block if resolving to the default dev DB and not in a temp path
                is_prod_db = "/local_forge_os/.localforge/localforge.db" in normalized_abs
                temp_roots = {
                    os.path.abspath(path).lower().replace("\\", "/")
                    for path in {
                        tempfile.gettempdir(),
                        os.getenv("TMP", ""),
                        os.getenv("TEMP", ""),
                    }
                    if path
                }
                in_temp = any(
                    normalized_abs.startswith(f"{temp_root}/")
                    or normalized_abs == temp_root
                    for temp_root in temp_roots
                )
                if is_prod_db and not in_temp:
                    raise RuntimeError(
                        "Database bootstrap BLOCKED: Attempting to write to the "
                        f"primary development database ({abs_db_path}) under pytest. "
                        "Please isolate tests using tmp_path and a temporary URL."
                    )

    await ensure_db_directory(db_manager.db_url)

    async with await db_manager.get_session() as session:
        current_version = await get_current_schema_version(session)
        logger.info(f"Current database schema version: {current_version}")

        if current_version == 0:



            logger.info(f"Initializing new database schema (Version {CURRENT_VERSION})...")
            # In SQLAlchemy async, we run create_all on the sync connection within a run_sync block
            async with db_manager.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            version_record = SchemaVersionORM(version=CURRENT_VERSION)
            session.add(version_record)
            await session.commit()

            # Seed pricing snapshots
            await seed_pricing_data(session)

            logger.info("Database schema initialized successfully.")
            return CURRENT_VERSION

        elif current_version < CURRENT_VERSION:
            logger.info(
                f"Migrating database from version {current_version} to {CURRENT_VERSION}..."
            )
            async with db_manager.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                if current_version < 3:
                    columns = await conn.execute(text("PRAGMA table_info(memory_facts)"))
                    column_names = {str(row[1]) for row in columns.fetchall()}
                    if "kind" not in column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE memory_facts "
                                "ADD COLUMN kind VARCHAR(50) NOT NULL DEFAULT 'stack_fact'"
                            )
                        )
            session.add(SchemaVersionORM(version=CURRENT_VERSION))
            await session.commit()

            # Seed pricing snapshots
            await seed_pricing_data(session)

            return CURRENT_VERSION

        else:
            logger.info("Database is already up to date.")
            return current_version


async def seed_pricing_data(session: AsyncSession) -> None:
    from localforge.storage.orm import PricingSourceORM, ModelPricingSnapshotORM
    from sqlalchemy import select

    # Check if pricing sources already exist
    existing = await session.execute(select(PricingSourceORM).limit(1))
    if existing.first():
        return

    logger.info("Seeding competitor model pricing snapshots into database...")

    # 1. OpenAI Source
    openai_src = PricingSourceORM(
        provider="OpenAI",
        url="https://openai.com/api/pricing/",
        notes="Official OpenAI pricing snapshots baseline."
    )
    session.add(openai_src)

    # 2. Anthropic Source
    anthropic_src = PricingSourceORM(
        provider="Anthropic",
        url="https://platform.claude.com/docs/en/about-claude/pricing",
        notes="Official Anthropic pricing snapshots baseline."
    )
    session.add(anthropic_src)

    # 3. Google Source
    google_src = PricingSourceORM(
        provider="Google",
        url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Official Google pricing snapshots baseline."
    )
    session.add(google_src)
    await session.flush() # Populate IDs

    # OpenAI snapshots (per 1M tokens)
    openai_snapshots = [
        ModelPricingSnapshotORM(pricing_source_id=openai_src.id, model_name="gpt-5.5-large", input_price_per_million=5.00, output_price_per_million=30.00),
        ModelPricingSnapshotORM(pricing_source_id=openai_src.id, model_name="gpt-5.4-medium", input_price_per_million=2.50, output_price_per_million=15.00),
        ModelPricingSnapshotORM(pricing_source_id=openai_src.id, model_name="gpt-5.4-mini", input_price_per_million=0.75, output_price_per_million=4.50),
    ]

    # Anthropic snapshots (per 1M tokens)
    anthropic_snapshots = [
        ModelPricingSnapshotORM(pricing_source_id=anthropic_src.id, model_name="claude-opus-4.8", input_price_per_million=5.00, output_price_per_million=25.00),
        ModelPricingSnapshotORM(pricing_source_id=anthropic_src.id, model_name="claude-sonnet-4.6", input_price_per_million=3.00, output_price_per_million=15.00),
        ModelPricingSnapshotORM(pricing_source_id=anthropic_src.id, model_name="claude-haiku-4.5", input_price_per_million=1.00, output_price_per_million=5.00),
    ]

    # Google snapshots (per 1M tokens)
    google_snapshots = [
        ModelPricingSnapshotORM(pricing_source_id=google_src.id, model_name="gemini-2.5-pro", input_price_per_million=1.25, output_price_per_million=10.00),
        ModelPricingSnapshotORM(pricing_source_id=google_src.id, model_name="gemini-2.5-flash", input_price_per_million=0.30, output_price_per_million=2.50),
        ModelPricingSnapshotORM(pricing_source_id=google_src.id, model_name="gemini-2.5-flash-lite", input_price_per_million=0.10, output_price_per_million=0.40),
    ]

    for snap in openai_snapshots + anthropic_snapshots + google_snapshots:
        session.add(snap)

    await session.commit()
    logger.info("Pricing snapshots seeded successfully.")
