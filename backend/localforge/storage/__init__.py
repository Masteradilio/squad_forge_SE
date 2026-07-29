"""Storage package public boundary.

The package intentionally avoids eager imports. Storage modules are used by
services during startup, and importing transaction-bound helpers here can create
clean-interpreter cycles when a public module imports only one storage leaf.
"""

from typing import Any

__all__ = [
    "Base",
    "DatabaseManager",
    "db_manager",
    "get_db_session",
    "bootstrap_database",
    "get_current_schema_version",
    "sqlite_path_from_url",
    "backup_sqlite_database",
    "restore_sqlite_database",
    "UnsupportedSchemaVersionError",
    "UnitOfWork",
    "ArtifactStore",
    "ArtifactStoreError",
]

_STORAGE_IMPORTS = {
    "Base": ("localforge.storage.orm", "Base"),
    "DatabaseManager": ("localforge.storage.database", "DatabaseManager"),
    "db_manager": ("localforge.storage.database", "db_manager"),
    "get_db_session": ("localforge.storage.database", "get_db_session"),
    "bootstrap_database": ("localforge.storage.bootstrap", "bootstrap_database"),
    "get_current_schema_version": ("localforge.storage.bootstrap", "get_current_schema_version"),
    "sqlite_path_from_url": ("localforge.storage.bootstrap", "sqlite_path_from_url"),
    "backup_sqlite_database": ("localforge.storage.bootstrap", "backup_sqlite_database"),
    "restore_sqlite_database": ("localforge.storage.bootstrap", "restore_sqlite_database"),
    "UnsupportedSchemaVersionError": (
        "localforge.storage.bootstrap",
        "UnsupportedSchemaVersionError",
    ),
    "UnitOfWork": ("localforge.storage.transactions", "UnitOfWork"),
    "ArtifactStore": ("localforge.storage.artifacts", "ArtifactStore"),
    "ArtifactStoreError": ("localforge.storage.artifacts", "ArtifactStoreError"),
}


def __getattr__(name: str) -> Any:
    if name not in _STORAGE_IMPORTS:
        raise AttributeError(name)
    module_name, object_name = _STORAGE_IMPORTS[name]
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, object_name)
    globals()[name] = value
    return value
