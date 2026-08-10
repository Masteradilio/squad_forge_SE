import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from scripts.probe_redis import (
    probe_database_authority,
    redact_redis_url,
    resolve_default_redis_url,
    summarize_probe,
)


def test_redis_probe_redacts_credentials():
    assert redact_redis_url("redis://user:secret@example.test:6379/0") == "redis://user:***@example.test:6379/0"
    assert redact_redis_url("redis://example.test:6379/0") == "redis://example.test:6379/0"


def test_redis_probe_defaults_to_host_port_when_no_service_url_is_configured(monkeypatch):
    for name in ("REDIS_URL", "LOCALFORGE_REDIS_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REDIS_PASSWORD", "local/pass")
    monkeypatch.setenv("REDIS_HOST_PORT", "16379")

    assert resolve_default_redis_url() == "redis://:local%2Fpass@127.0.0.1:16379/0"


def test_redis_probe_requires_cache_pubsub_and_exclusive_lock():
    result = summarize_probe(
        cache_ok=True,
        pubsub_ok=True,
        lock_exclusive=False,
        concurrent_lock=True,
        available=True,
    )
    assert result["status"] == "BLOCKED"
    assert "lock" in result["reason"]

    result = summarize_probe(
        cache_ok=True,
        pubsub_ok=True,
        lock_exclusive=True,
        concurrent_lock=False,
        available=True,
    )
    assert result["status"] == "BLOCKED"

    result = summarize_probe(
        cache_ok=True,
        pubsub_ok=True,
        lock_exclusive=True,
        concurrent_lock=True,
        lease_expiry_ok=True,
        fail_closed_ok=True,
        database_authority_ok=True,
        available=True,
    )
    assert result["status"] == "PASS"

    not_proven = summarize_probe(
        cache_ok=True,
        pubsub_ok=True,
        lock_exclusive=True,
        concurrent_lock=True,
        lease_expiry_ok=True,
        fail_closed_ok=True,
        database_authority_ok=None,
        available=True,
    )
    assert not_proven["status"] == "NOT_PROVEN"


@pytest.mark.asyncio
async def test_database_authority_probe_uses_a_temporary_transaction(tmp_path):
    from localforge.services.redis_manager import RedisManager

    manager = RedisManager(redis_url="redis://non-existent-host:9999/0")
    result = await probe_database_authority(
        f"sqlite+aiosqlite:///{tmp_path / 'authority.db'}",
        redis_manager=manager,
        key_prefix="test:authority",
    )
    await manager.close()

    assert result["status"] == "PASS"
    assert result["witness"] == "temporary_database_transaction"


def test_redis_probe_script_reports_blocked_without_live_server(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/probe_redis.py",
            "--url",
            "redis://127.0.0.1:63999/0",
            "--output",
            str(tmp_path / "redis.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads((tmp_path / "redis.json").read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED"
    assert "secret" not in json.dumps(payload).lower()
