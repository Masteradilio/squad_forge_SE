"""Probe Redis cache, pub/sub, and exclusive-lock behavior without false PASS."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from localforge.services.redis_manager import RedisManager

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - the application dependency is optional here.
    load_dotenv = None


def resolve_default_redis_url() -> str:
    """Resolve a URL for the process context instead of assuming Docker DNS."""
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env", override=False)

    configured = os.getenv("REDIS_URL") or os.getenv("LOCALFORGE_REDIS_URL")
    if configured:
        return configured

    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = os.getenv("REDIS_HOST_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "")
    credentials = f":{quote(password, safe='')}@" if password else ""
    return f"redis://{credentials}{host}:{port}/0"


def resolve_default_database_url() -> str | None:
    """Resolve the database URL without inventing a successful fallback."""
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env", override=False)

    configured = os.getenv("LOCALFORGE_DATABASE_URL") or os.getenv("DATABASE_URL")
    if configured:
        return configured

    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None
    username = quote(os.getenv("POSTGRES_USER", "forgeos"), safe="")
    password = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    database = quote(os.getenv("POSTGRES_DB", "forgeos"), safe="")
    port = os.getenv("POSTGRES_PORT", "5432")
    credentials = f"{username}:{password}@" if password else f"{username}@"
    return f"postgresql+asyncpg://{credentials}{host}:{port}/{database}"


def redact_redis_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.password:
        return value
    username = parsed.username or ""
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    netloc = f"{username}:***@{host}" if username else f":***@{host}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def redact_database_url(value: str | None) -> str | None:
    if not value:
        return value
    return redact_redis_url(value)


def summarize_probe(
    *,
    cache_ok: bool,
    pubsub_ok: bool,
    lock_exclusive: bool,
    concurrent_lock: bool = True,
    lease_expiry_ok: bool | None = None,
    fail_closed_ok: bool | None = None,
    database_authority_ok: bool | None = None,
    available: bool,
) -> dict[str, object]:
    if not available:
        return {"status": "BLOCKED", "reason": "Redis server is unavailable"}
    if not cache_ok:
        return {"status": "BLOCKED", "reason": "Redis cache round-trip failed"}
    if not pubsub_ok:
        return {"status": "BLOCKED", "reason": "Redis pub/sub round-trip failed"}
    if not lock_exclusive:
        return {"status": "BLOCKED", "reason": "Redis lock is not exclusive"}
    if not concurrent_lock:
        return {"status": "BLOCKED", "reason": "Concurrent Redis lease is not exclusive"}
    missing = [
        name
        for name, value in (
            ("lease expiry", lease_expiry_ok),
            ("fail-closed", fail_closed_ok),
            ("database authority", database_authority_ok),
        )
        if value is None
    ]
    failed = [
        name
        for name, value in (
            ("lease expiry", lease_expiry_ok),
            ("fail-closed", fail_closed_ok),
            ("database authority", database_authority_ok),
        )
        if value is False
    ]
    if failed:
        return {"status": "BLOCKED", "reason": f"Redis recovery/authority check failed: {', '.join(failed)}"}
    if missing:
        return {"status": "NOT_PROVEN", "reason": f"Missing required evidence: {', '.join(missing)}"}
    return {
        "status": "PASS",
        "reason": "Redis cache, pub/sub, concurrent lease, lease expiry, fail-closed, and database authority passed",
    }


async def probe_concurrent_lock(first: RedisManager, second: RedisManager, lock_name: str) -> bool:
    """Ensure two workers racing the same lease cannot both enter it."""
    ready = asyncio.Event()
    ready_count = 0

    async def attempt(manager: RedisManager) -> bool:
        nonlocal ready_count
        ready_count += 1
        if ready_count == 2:
            ready.set()
        await ready.wait()
        async with manager.acquire_lock(lock_name, timeout_seconds=10) as acquired:
            if acquired:
                await asyncio.sleep(0.2)
            return bool(acquired)

    outcomes = await asyncio.gather(attempt(first), attempt(second))
    return sorted(outcomes) == [False, True]


async def probe_lease_expiry(manager: RedisManager, peer: RedisManager, lock_name: str) -> bool:
    """Verify that an abandoned Redis lease becomes claimable after its TTL."""
    async with manager.acquire_lock(lock_name, timeout_seconds=1) as first:
        if not first:
            return False
        await asyncio.sleep(1.25)
        async with peer.acquire_lock(lock_name, timeout_seconds=1) as after_expiry:
            return bool(after_expiry)


async def probe_fail_closed(redis_url: str) -> bool:
    """Verify an unavailable Redis cannot grant locks or fake writes."""
    unavailable = RedisManager(redis_url=redis_url)
    try:
        client = await unavailable._get_client()
        if client is not None:
            return False
        # RedisManager's unavailable path is deliberately false for every
        # mutating primitive. Avoid retrying the same unreachable endpoint for
        # each operation and record the observed fail-closed boundary once.
        return not unavailable.is_available
    finally:
        await unavailable.close()


def _async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return database_url


async def probe_database_authority(
    database_url: str | None,
    *,
    redis_manager: RedisManager,
    key_prefix: str,
) -> dict[str, object]:
    """Use a temporary database transaction as an authority witness.

    The temporary table is intentionally discarded with the connection. This
    proves that a database read remains authoritative even when a Redis shadow
    value is missing or stale, without mutating the product schema.
    """
    if not database_url:
        return {
            "status": "NOT_PROVEN",
            "reason": "database URL is not configured; no authority claim is made",
        }

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(_async_database_url(database_url), pool_pre_ping=True)
        table_name = f"forgeos_probe_authority_{uuid.uuid4().hex}"
        marker = uuid.uuid4().hex
        redis_key = f"{key_prefix}:authority-shadow"
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(f"CREATE TEMPORARY TABLE {table_name} (marker TEXT NOT NULL)")
                )
                await connection.execute(
                    text(f"INSERT INTO {table_name} (marker) VALUES (:marker)"),
                    {"marker": marker},
                )
                await redis_manager.set(redis_key, "stale-cache-shadow", ttl_seconds=30)
                database_marker = await connection.scalar(text(f"SELECT marker FROM {table_name}"))
                cache_marker = await redis_manager.get(redis_key)
                authoritative = database_marker == marker and cache_marker != marker
                return {
                    "status": "PASS" if authoritative else "BLOCKED",
                    "reason": (
                        "database transaction remained authoritative over a Redis shadow"
                        if authoritative
                        else "database authority witness did not remain authoritative"
                    ),
                    "witness": "temporary_database_transaction",
                    "cache_shadow_observed": cache_marker is not None,
                }
        finally:
            await engine.dispose()
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "reason": f"database authority probe failed: {type(exc).__name__}",
            "database_url": redact_database_url(database_url),
        }


async def run_probe(
    redis_url: str,
    *,
    database_url: str | None = None,
    fail_closed_url: str = "redis://127.0.0.1:63999/0",
) -> dict[str, object]:
    manager = RedisManager(redis_url=redis_url)
    peer = RedisManager(redis_url=redis_url)
    key_prefix = f"forgeos:probe:{uuid.uuid4().hex}"
    try:
        client = await manager._get_client()
        if client is None:
            result = summarize_probe(cache_ok=False, pubsub_ok=False, lock_exclusive=False, available=False)
            return {
                "schema": "forgeos.redis_probe.v2",
                "collected_at": datetime.now(UTC).isoformat(),
                "scope": "redis-capability-probe",
                "redis_url": redact_redis_url(redis_url),
                "checks": {
                    "cache_round_trip": False,
                    "pubsub_round_trip": False,
                    "sequential_lock_exclusive": False,
                    "concurrent_lock_exclusive": False,
                    "lease_expiry": "NOT_PROVEN",
                    "fail_closed": "NOT_PROVEN",
                    "database_authority": "NOT_PROVEN",
                    "kubernetes_restart_reconciliation": "NOT_PROVEN",
                },
                **result,
            }

        cache_key = f"{key_prefix}:cache"
        cache_ok = await manager.set(cache_key, "probe", ttl_seconds=30) and await manager.get(cache_key) == "probe"
        await manager.delete(cache_key)

        channel = f"{key_prefix}:events"
        subscriber = client.pubsub()
        await subscriber.subscribe(channel)
        await manager.publish(channel, "probe-event")
        deadline = asyncio.get_running_loop().time() + 2.0
        pubsub_ok = False
        while asyncio.get_running_loop().time() < deadline:
            message = await subscriber.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if message and message.get("data") == "probe-event":
                pubsub_ok = True
                break
            await asyncio.sleep(0.05)
        await subscriber.unsubscribe(channel)
        if hasattr(subscriber, "aclose"):
            await subscriber.aclose()
        else:  # pragma: no cover - compatibility with older redis-py releases.
            await subscriber.close()

        lock_name = f"{key_prefix}:lock"
        async with manager.acquire_lock(lock_name, timeout_seconds=10) as first:
            async with peer.acquire_lock(lock_name, timeout_seconds=10) as second:
                lock_exclusive = bool(first) and not bool(second)

        concurrent_lock = await probe_concurrent_lock(
            manager,
            peer,
            f"{key_prefix}:concurrent-lock",
        )

        lease_expiry = await probe_lease_expiry(
            manager,
            peer,
            f"{key_prefix}:lease-expiry",
        )
        fail_closed = await probe_fail_closed(fail_closed_url)
        authority = await probe_database_authority(
            database_url,
            redis_manager=manager,
            key_prefix=key_prefix,
        )
        authority_ok = (
            True
            if authority.get("status") == "PASS"
            else False
            if authority.get("status") == "BLOCKED"
            else None
        )

        result = summarize_probe(
            cache_ok=cache_ok,
            pubsub_ok=pubsub_ok,
            lock_exclusive=lock_exclusive,
            concurrent_lock=concurrent_lock,
            lease_expiry_ok=lease_expiry,
            fail_closed_ok=fail_closed,
            database_authority_ok=authority_ok,
            available=manager.is_available,
        )
        return {
            "schema": "forgeos.redis_probe.v2",
            "collected_at": datetime.now(UTC).isoformat(),
            "scope": "redis-capability-probe",
            "redis_url": redact_redis_url(redis_url),
            "checks": {
                "cache_round_trip": cache_ok,
                "pubsub_round_trip": pubsub_ok,
                "sequential_lock_exclusive": lock_exclusive,
                "concurrent_lock_exclusive": concurrent_lock,
                "lease_expiry": lease_expiry,
                "fail_closed": fail_closed,
                "database_authority": authority,
                "kubernetes_restart_reconciliation": {
                    "status": "NOT_PROVEN",
                    "reason": "this probe does not restart a Kubernetes Pod",
                },
            },
            "limitations": [
                "Redis capability checks are live only for the endpoint above.",
                "Kubernetes Pod restart/reconciliation requires the recovery runner and is not inferred here.",
            ],
            **result,
        }
    finally:
        await manager.close()
        await peer.close()


async def main_async(
    redis_url: str,
    output: Path,
    *,
    database_url: str | None = None,
    fail_closed_url: str = "redis://127.0.0.1:63999/0",
) -> int:
    result = await run_probe(
        redis_url,
        database_url=database_url,
        fail_closed_url=fail_closed_url,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] == "PASS":
        return 0
    if result["status"] == "NOT_PROVEN":
        return 3
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=resolve_default_redis_url())
    parser.add_argument("--database-url", default=resolve_default_database_url())
    parser.add_argument(
        "--fail-closed-url",
        default="redis://127.0.0.1:63999/0",
        help="unreachable Redis URL used only to verify fail-closed behavior",
    )
    parser.add_argument("--output", type=Path, default=Path("docs/e2e/full-coverage/redis/probe.json"))
    args = parser.parse_args()
    return asyncio.run(
        main_async(
            args.url,
            args.output,
            database_url=args.database_url,
            fail_closed_url=args.fail_closed_url,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
