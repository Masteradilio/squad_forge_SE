"""Redis Service Manager — In-memory caching, Pub/Sub event streaming, and distributed locks with graceful fallback."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    aioredis = None  # type: ignore


class RedisManager:
    """Manages Redis connections for caching, Pub/Sub, and distributed locks."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or os.getenv("LOCALFORGE_REDIS_URL") or os.getenv("REDIS_URL")
        if not self.redis_url:
            host = os.getenv("REDIS_HOST", "redis")
            port = os.getenv("REDIS_PORT", "6379")
            database = os.getenv("REDIS_DB", "0")
            password = quote(os.getenv("REDIS_PASSWORD", ""), safe="")
            credentials = f":{password}@" if password else ""
            self.redis_url = f"redis://{credentials}{host}:{port}/{database}"
        self._client: Any | None = None
        self._available: bool = False

    async def _get_client(self) -> Any | None:
        if not HAS_REDIS:
            return None
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self.redis_url, decode_responses=True, socket_connect_timeout=2.0
                )
                await self._client.ping()
                self._available = True
                logger.info(f"Connected to Redis at {self.redis_url}")
            except Exception as exc:
                logger.debug(f"Redis unavailable ({exc}), operating in memory fallback mode.")
                self._available = False
                self._client = None
        return self._client

    @property
    def is_available(self) -> bool:
        return self._available

    async def get(self, key: str) -> str | None:
        """Retrieve a cached string value from Redis."""
        client = await self._get_client()
        if not client:
            return None
        try:
            return await client.get(key)
        except Exception as exc:
            logger.debug(f"Redis GET failed for key {key}: {exc}")
            return None

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Store a string value in Redis with optional TTL."""
        client = await self._get_client()
        if not client:
            return False
        try:
            if ttl_seconds:
                await client.setex(key, ttl_seconds, value)
            else:
                await client.set(key, value)
            return True
        except Exception as exc:
            logger.debug(f"Redis SET failed for key {key}: {exc}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        client = await self._get_client()
        if not client:
            return False
        try:
            await client.delete(key)
            return True
        except Exception as exc:
            logger.debug(f"Redis DELETE failed for key {key}: {exc}")
            return False

    async def publish(self, channel: str, message: str) -> bool:
        """Publish a message to a Redis Pub/Sub channel."""
        client = await self._get_client()
        if not client:
            return False
        try:
            await client.publish(channel, message)
            return True
        except Exception as exc:
            logger.debug(f"Redis PUBLISH failed for channel {channel}: {exc}")
            return False

    @asynccontextmanager
    async def acquire_lock(
        self, lock_name: str, timeout_seconds: int = 10
    ) -> AsyncGenerator[bool, None]:
        """Acquire a distributed lock with automatic expiration."""
        client = await self._get_client()
        lock_key = f"lock:{lock_name}"
        lock_acquired = False
        if client:
            try:
                # Try acquiring lock atomically using setnx
                lock_acquired = bool(
                    await client.set(lock_key, "locked", px=timeout_seconds * 1000, nx=True)
                )
            except Exception as exc:
                logger.debug(f"Redis lock acquisition error for {lock_name}: {exc}")
                lock_acquired = False
        try:
            yield lock_acquired
        finally:
            if client and lock_acquired:
                try:
                    await client.delete(lock_key)
                except Exception:
                    pass

    async def close(self) -> None:
        """Close the Redis client connection."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
            self._available = False


# Global default instance
redis_manager = RedisManager()
