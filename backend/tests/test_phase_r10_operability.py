import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.services.security_controls import ensure_relative_to, redact_secrets
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_api_auth_is_required_when_token_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALFORGE_API_TOKEN", "test-token-123")
    manager = _make_db_manager(tmp_path)
    try:
        client = TestClient(create_app(db_manager=manager))

        assert client.get("/health").status_code == 200
        assert client.get("/ready").json()["auth_required"] is True
        assert client.get("/projects").status_code == 401
        assert client.get(
            "/projects",
            headers={"Authorization": "Bearer test-token-123"},
        ).status_code == 200
    finally:
        asyncio.run(manager.close())


def test_api_rejects_oversized_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALFORGE_MAX_BODY_BYTES", "1024")
    manager = _make_db_manager(tmp_path)
    try:
        client = TestClient(create_app(db_manager=manager))

        response = client.post("/not-found", content=b"x" * 2048)

        assert response.status_code == 413
    finally:
        asyncio.run(manager.close())


def test_secret_redaction_covers_environment_and_inline_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret-value-123")

    redacted = redact_secrets(
        "api_key=inline-secret-456 token: another-secret-789 "
        "Authorization: Bearer bearer-secret-000 or-secret-value-123"
    )

    assert "or-secret-value-123" not in redacted
    assert "inline-secret-456" not in redacted
    assert "another-secret-789" not in redacted
    assert "bearer-secret-000" not in redacted


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    assert ensure_relative_to(root, root / "app.py") == (root / "app.py").resolve()
    with pytest.raises(ValueError, match="escapes configured root"):
        ensure_relative_to(root, Path(tmp_path) / "outside.py")


def _make_db_manager(tmp_path: Path) -> DatabaseManager:
    db_file = (tmp_path / "r10.db").as_posix()
    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_file}")
    asyncio.run(bootstrap_database(manager))
    return manager
