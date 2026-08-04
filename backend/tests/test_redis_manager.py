"""Unit tests for RedisManager service and transparent fallback behavior."""

from unittest.mock import AsyncMock, patch

import pytest
from localforge.services.redis_manager import RedisManager, redis_manager


@pytest.mark.asyncio
async def test_redis_manager_fallback_when_unavailable():
    """Verify RedisManager returns graceful fallbacks when Redis server is unconfigured or unreachable."""
    manager = RedisManager(redis_url="redis://non-existent-host:9999/0")
    
    # Check fallback returns
    val = await manager.get("test_key")
    assert val is None

    set_res = await manager.set("test_key", "value", ttl_seconds=60)
    assert set_res is False

    del_res = await manager.delete("test_key")
    assert del_res is False

    pub_res = await manager.publish("test_channel", "msg")
    assert pub_res is False


@pytest.mark.asyncio
async def test_redis_manager_mock_operations():
    """Verify RedisManager handles GET, SET, DELETE, PUBLISH and acquire_lock when client is active."""
    manager = RedisManager(redis_url="redis://localhost:6379/0")
    
    mock_client = AsyncMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = "cached_value"
    mock_client.set.return_value = True
    mock_client.setex.return_value = True
    mock_client.delete.return_value = 1
    mock_client.publish.return_value = 1

    with patch.object(manager, "_get_client", return_value=mock_client):
        assert await manager.get("my_key") == "cached_value"
        assert await manager.set("my_key", "val", ttl_seconds=10) is True
        assert await manager.delete("my_key") is True
        assert await manager.publish("my_chan", "hello") is True

        async with manager.acquire_lock("agent_action_lock", timeout_seconds=5) as acquired:
            assert acquired is True


@pytest.mark.asyncio
async def test_global_redis_manager_instance():
    """Verify global redis_manager instance exports property and client interface."""
    assert hasattr(redis_manager, "is_available")
    assert hasattr(redis_manager, "acquire_lock")
