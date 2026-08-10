from localforge.storage.database import resolve_database_url


def test_database_component_configuration_url_encodes_reserved_password(monkeypatch):
    for name in ("LOCALFORGE_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "forgeos")
    monkeypatch.setenv("POSTGRES_USER", "forgeos")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:#%")

    assert resolve_database_url() == "postgresql+asyncpg://forgeos:p%40ss%3A%23%25@postgres:5432/forgeos"
