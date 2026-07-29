import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.storage.database import DatabaseManager
from localforge.storage.orm import Base, SchemaVersionORM

logger = logging.getLogger(__name__)

CURRENT_VERSION = 18


class UnsupportedSchemaVersionError(RuntimeError):
    """Raised when a database was written by a newer LocalForge schema."""


def sqlite_path_from_url(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite+aiosqlite:///"):
        return None
    db_path = db_url[len("sqlite+aiosqlite:///") :]
    if db_path == ":memory:":
        return None
    if db_path.startswith("/") and len(db_path) > 2 and db_path[2] == ":":
        db_path = db_path[1:]
    return Path(db_path).expanduser().resolve()


def backup_sqlite_database(db_url: str, backup_dir: str | Path | None = None) -> Path:
    db_path = sqlite_path_from_url(db_url)
    if db_path is None:
        raise ValueError("SQLite file backup requires a sqlite+aiosqlite file URL.")
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    target_dir = Path(backup_dir) if backup_dir is not None else db_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = target_dir / f"{db_path.stem}.schema-backup.{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def restore_sqlite_database(backup_path: str | Path, target_path: str | Path) -> Path:
    source = Path(backup_path).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


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
                    normalized_abs.startswith(f"{temp_root}/") or normalized_abs == temp_root
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
                if current_version < 15:
                    graph_columns = await conn.execute(
                        text("PRAGMA table_info(graph_mutation_journal)")
                    )
                    graph_column_names = {str(row[1]) for row in graph_columns.fetchall()}
                    if "mutation_sequence" not in graph_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE graph_mutation_journal "
                                "ADD COLUMN mutation_sequence INTEGER "
                                "NOT NULL DEFAULT 0"
                            )
                        )
                        await conn.execute(
                            text(
                                "UPDATE graph_mutation_journal "
                                "SET mutation_sequence = graph_version"
                            )
                        )

                    deep_run_columns = await conn.execute(
                        text("PRAGMA table_info(deep_swarm_runs)")
                    )
                    deep_run_column_names = {str(row[1]) for row in deep_run_columns.fetchall()}
                    if "node_side_effect_keys_json" not in deep_run_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE deep_swarm_runs "
                                "ADD COLUMN node_side_effect_keys_json JSON "
                                "NOT NULL DEFAULT '{}'"
                            )
                        )
                    if "completed_side_effect_keys_json" not in deep_run_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE deep_swarm_runs "
                                "ADD COLUMN completed_side_effect_keys_json JSON "
                                "NOT NULL DEFAULT '[]'"
                            )
                        )
                    await conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS "
                            "uq_graph_mutation_plan_sequence "
                            "ON graph_mutation_journal "
                            "(plan_id, mutation_sequence)"
                        )
                    )
                    await conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS "
                            "uq_graph_mutation_plan_version "
                            "ON graph_mutation_journal "
                            "(plan_id, graph_version)"
                        )
                    )
                if current_version < 16:
                    path_columns = await conn.execute(text("PRAGMA table_info(path_leases)"))
                    path_column_names = {str(row[1]) for row in path_columns.fetchall()}
                    if "normalized_target_path" not in path_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE path_leases "
                                "ADD COLUMN normalized_target_path TEXT NOT NULL DEFAULT ''"
                            )
                        )
                        await conn.execute(
                            text(
                                "UPDATE path_leases "
                                "SET normalized_target_path = replace(target_path, '\\', '/')"
                            )
                        )
                    if "active_conflict_key" not in path_column_names:
                        await conn.execute(
                            text("ALTER TABLE path_leases ADD COLUMN active_conflict_key TEXT")
                        )
                        await conn.execute(
                            text(
                                "UPDATE path_leases "
                                "SET active_conflict_key = normalized_target_path "
                                "WHERE release_reason IS NULL"
                            )
                        )
                    if "heartbeat_at" not in path_column_names:
                        await conn.execute(
                            text("ALTER TABLE path_leases ADD COLUMN heartbeat_at DATETIME")
                        )
                        await conn.execute(
                            text("UPDATE path_leases SET heartbeat_at = created_at")
                        )
                    if "attempt_number" not in path_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE path_leases "
                                "ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1"
                            )
                        )
                    if "worktree_path" not in path_column_names:
                        await conn.execute(
                            text("ALTER TABLE path_leases ADD COLUMN worktree_path TEXT")
                        )
                    if "fencing_token" not in path_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE path_leases "
                                "ADD COLUMN fencing_token VARCHAR(255) NOT NULL DEFAULT ''"
                            )
                        )
                        await conn.execute(
                            text(
                                "UPDATE path_leases "
                                "SET fencing_token = 'legacy-path-lease-' || id "
                                "WHERE fencing_token = ''"
                            )
                        )
                    await conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS "
                            "uq_path_lease_active_exact "
                            "ON path_leases (project_id, active_conflict_key)"
                        )
                    )

                    dispatch_columns = await conn.execute(
                        text("PRAGMA table_info(runner_dispatch_logs)")
                    )
                    dispatch_column_names = {str(row[1]) for row in dispatch_columns.fetchall()}
                    if "lease_token" not in dispatch_column_names:
                        await conn.execute(
                            text("ALTER TABLE runner_dispatch_logs ADD COLUMN lease_token VARCHAR(255)")
                        )
                    if "lease_owner_id" not in dispatch_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE runner_dispatch_logs "
                                "ADD COLUMN lease_owner_id VARCHAR(255)"
                            )
                        )
                    if "lease_expires_at" not in dispatch_column_names:
                        await conn.execute(
                            text("ALTER TABLE runner_dispatch_logs ADD COLUMN lease_expires_at DATETIME")
                        )
                    if "heartbeat_at" not in dispatch_column_names:
                        await conn.execute(
                            text("ALTER TABLE runner_dispatch_logs ADD COLUMN heartbeat_at DATETIME")
                        )

                if current_version < 17:
                    loop_run_columns = await conn.execute(text("PRAGMA table_info(loop_runs)"))
                    loop_run_column_names = {str(row[1]) for row in loop_run_columns.fetchall()}
                    if "triage_input_json" not in loop_run_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE loop_runs "
                                "ADD COLUMN triage_input_json JSON NOT NULL DEFAULT '{}'"
                            )
                        )
                    if "triage_classification" not in loop_run_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE loop_runs "
                                "ADD COLUMN triage_classification VARCHAR(50) "
                                "NOT NULL DEFAULT 'PENDING'"
                            )
                        )
                    if "triage_decision" not in loop_run_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE loop_runs "
                                "ADD COLUMN triage_decision TEXT NOT NULL DEFAULT 'PENDING'"
                            )
                        )
                    if "triage_task_ids_json" not in loop_run_column_names:
                        await conn.execute(
                            text(
                                "ALTER TABLE loop_runs "
                                "ADD COLUMN triage_task_ids_json JSON NOT NULL DEFAULT '[]'"
                            )
                        )

                if current_version < 18:
                    await conn.execute(
                        text(
                            """
                            CREATE TABLE IF NOT EXISTS path_lease_waits (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                                task_run_id INTEGER NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
                                owner_id VARCHAR(255) NOT NULL,
                                target_path TEXT NOT NULL,
                                normalized_target_path TEXT NOT NULL,
                                blocking_owner_id VARCHAR(255),
                                blocking_lease_id INTEGER REFERENCES path_leases(id) ON DELETE SET NULL,
                                status VARCHAR(50) NOT NULL DEFAULT 'WAITING',
                                queue_position INTEGER NOT NULL DEFAULT 1,
                                requested_at DATETIME,
                                expires_at DATETIME NOT NULL,
                                resolved_at DATETIME,
                                reason TEXT
                            )
                            """
                        )
                    )
                    await conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_path_lease_waits_active "
                            "ON path_lease_waits(project_id, status, normalized_target_path, requested_at)"
                        )
                    )

            # Phase 10 / Schema v15 Migration: Memory provenance columns and memory_relations table
            if current_version < 15:
                async with db_manager.engine.begin() as conn:
                    result = await conn.execute(text("PRAGMA table_info(memory_facts)"))
                    memory_fact_columns = {row[1] for row in result.fetchall()}

                    if "repository" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN repository TEXT")
                        )
                    if "run_id" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN run_id INTEGER")
                        )
                    if "task_key" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN task_key VARCHAR(100)")
                        )
                    if "attempt_number" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN attempt_number INTEGER")
                        )
                    if "artifact_id" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN artifact_id INTEGER")
                        )
                    if "verifier" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN verifier VARCHAR(255)")
                        )
                    if "validity" not in memory_fact_columns:
                        await conn.execute(
                            text(
                                "ALTER TABLE memory_facts ADD COLUMN validity VARCHAR(50) NOT NULL DEFAULT 'AUTHORITATIVE'"
                            )
                        )
                    if "confidence" not in memory_fact_columns:
                        await conn.execute(
                            text(
                                "ALTER TABLE memory_facts ADD COLUMN confidence FLOAT NOT NULL DEFAULT 1.0"
                            )
                        )
                    if "policy_scope" not in memory_fact_columns:
                        await conn.execute(
                            text("ALTER TABLE memory_facts ADD COLUMN policy_scope VARCHAR(255)")
                        )
                    if "category" not in memory_fact_columns:
                        await conn.execute(
                            text(
                                "ALTER TABLE memory_facts ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT 'OBSERVED_FACT'"
                            )
                        )

                    # Create memory_relations table if not existing
                    await conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS memory_relations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            source_fact_id INTEGER NOT NULL REFERENCES memory_facts(id) ON DELETE CASCADE,
                            target_fact_id INTEGER NOT NULL REFERENCES memory_facts(id) ON DELETE CASCADE,
                            relation_type VARCHAR(50) NOT NULL,
                            provenance_json JSON NOT NULL DEFAULT '{}',
                            created_at DATETIME
                        )
                    """)
                    )

            session.add(SchemaVersionORM(version=CURRENT_VERSION))
            await session.commit()

            # Seed pricing snapshots
            await seed_pricing_data(session)

            return CURRENT_VERSION

        elif current_version == CURRENT_VERSION:
            logger.info("Database is already up to date.")
            return current_version

        raise UnsupportedSchemaVersionError(
            f"Database schema version {current_version} is newer than supported "
            f"LocalForge schema {CURRENT_VERSION}. Refusing to mutate this database."
        )


async def seed_pricing_data(session: AsyncSession) -> None:
    from sqlalchemy import select

    from localforge.storage.orm import ModelPricingSnapshotORM, PricingSourceORM

    # Check if pricing sources already exist
    existing = await session.execute(select(PricingSourceORM).limit(1))
    if existing.first():
        return

    logger.info("Seeding competitor model pricing snapshots into database...")

    # 1. OpenAI Source
    openai_src = PricingSourceORM(
        provider="OpenAI",
        url="https://openai.com/api/pricing/",
        notes="Official OpenAI pricing snapshots baseline.",
    )
    session.add(openai_src)

    # 2. Anthropic Source
    anthropic_src = PricingSourceORM(
        provider="Anthropic",
        url="https://platform.claude.com/docs/en/about-claude/pricing",
        notes="Official Anthropic pricing snapshots baseline.",
    )
    session.add(anthropic_src)

    # 3. Google Source
    google_src = PricingSourceORM(
        provider="Google",
        url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Official Google pricing snapshots baseline.",
    )
    session.add(google_src)
    await session.flush()  # Populate IDs

    # OpenAI snapshots (per 1M tokens)
    openai_snapshots = [
        ModelPricingSnapshotORM(
            pricing_source_id=openai_src.id,
            model_name="gpt-5.5-large",
            input_price_per_million=5.00,
            output_price_per_million=30.00,
        ),
        ModelPricingSnapshotORM(
            pricing_source_id=openai_src.id,
            model_name="gpt-5.4-medium",
            input_price_per_million=2.50,
            output_price_per_million=15.00,
        ),
        ModelPricingSnapshotORM(
            pricing_source_id=openai_src.id,
            model_name="gpt-5.4-mini",
            input_price_per_million=0.75,
            output_price_per_million=4.50,
        ),
    ]

    # Anthropic snapshots (per 1M tokens)
    anthropic_snapshots = [
        ModelPricingSnapshotORM(
            pricing_source_id=anthropic_src.id,
            model_name="claude-opus-4.8",
            input_price_per_million=5.00,
            output_price_per_million=25.00,
        ),
        ModelPricingSnapshotORM(
            pricing_source_id=anthropic_src.id,
            model_name="claude-sonnet-4.6",
            input_price_per_million=3.00,
            output_price_per_million=15.00,
        ),
        ModelPricingSnapshotORM(
            pricing_source_id=anthropic_src.id,
            model_name="claude-haiku-4.5",
            input_price_per_million=1.00,
            output_price_per_million=5.00,
        ),
    ]

    # Google snapshots (per 1M tokens)
    google_snapshots = [
        ModelPricingSnapshotORM(
            pricing_source_id=google_src.id,
            model_name="gemini-2.5-pro",
            input_price_per_million=1.25,
            output_price_per_million=10.00,
        ),
        ModelPricingSnapshotORM(
            pricing_source_id=google_src.id,
            model_name="gemini-2.5-flash",
            input_price_per_million=0.30,
            output_price_per_million=2.50,
        ),
        ModelPricingSnapshotORM(
            pricing_source_id=google_src.id,
            model_name="gemini-2.5-flash-lite",
            input_price_per_million=0.10,
            output_price_per_million=0.40,
        ),
    ]

    for snap in openai_snapshots + anthropic_snapshots + google_snapshots:
        session.add(snap)

    await session.commit()
    logger.info("Pricing snapshots seeded successfully.")
