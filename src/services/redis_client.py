"""
Redis client for state management and caching.

Provides async interface for Redis operations with connection pooling.
"""

import json
from typing import Any

import redis.asyncio as redis

from ..config import get_settings
from ..utils import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self, url: str | None = None):
        """
        Initialize Redis client.

        Args:
            url: Redis connection URL. If not provided, uses settings.
        """
        self._url = url or get_settings().redis.url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self._client is None:
            self._client = redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("Connected to Redis")

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Disconnected from Redis")

    async def ping(self) -> bool:
        """Check if Redis is available."""
        if not self._client:
            await self.connect()
        try:
            await self._client.ping()
            return True
        except redis.RedisError as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    # Basic operations
    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        if not self._client:
            await self.connect()
        return await self._client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        expire_seconds: int | None = None,
    ) -> bool:
        """Set a value with optional expiration."""
        if not self._client:
            await self.connect()
        return await self._client.set(key, value, ex=expire_seconds)

    async def delete(self, key: str) -> int:
        """Delete a key."""
        if not self._client:
            await self.connect()
        return await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if not self._client:
            await self.connect()
        return await self._client.exists(key) > 0

    # JSON operations
    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Get a JSON value."""
        value = await self.get(key)
        if value:
            return json.loads(value)
        return None

    async def set_json(
        self,
        key: str,
        value: dict[str, Any],
        expire_seconds: int | None = None,
    ) -> bool:
        """Set a JSON value."""
        return await self.set(key, json.dumps(value), expire_seconds)

    # Hash operations
    async def hget(self, key: str, field: str) -> str | None:
        """Get a field from a hash."""
        if not self._client:
            await self.connect()
        return await self._client.hget(key, field)

    async def hset(self, key: str, field: str, value: str) -> int:
        """Set a field in a hash."""
        if not self._client:
            await self.connect()
        return await self._client.hset(key, field, value)

    async def hgetall(self, key: str) -> dict[str, str]:
        """Get all fields from a hash."""
        if not self._client:
            await self.connect()
        return await self._client.hgetall(key)

    async def hmset(self, key: str, mapping: dict[str, str]) -> bool:
        """Set multiple fields in a hash."""
        if not self._client:
            await self.connect()
        return await self._client.hset(key, mapping=mapping)

    # Lock operations
    async def acquire_lock(
        self,
        lock_name: str,
        holder: str,
        timeout_seconds: int = 300,
    ) -> bool:
        """
        Acquire a distributed lock.

        Args:
            lock_name: Name of the lock
            holder: Identifier of the lock holder
            timeout_seconds: Lock expiration time

        Returns:
            True if lock acquired, False otherwise
        """
        if not self._client:
            await self.connect()

        key = f"lock:{lock_name}"
        # Use SET NX (set if not exists) with expiration
        result = await self._client.set(
            key,
            holder,
            nx=True,
            ex=timeout_seconds,
        )
        if result:
            logger.debug(f"Lock acquired: {lock_name} by {holder}")
        return result is True

    async def release_lock(self, lock_name: str, holder: str) -> bool:
        """
        Release a distributed lock.

        Args:
            lock_name: Name of the lock
            holder: Identifier of the lock holder (must match)

        Returns:
            True if lock released, False if not owner
        """
        if not self._client:
            await self.connect()

        key = f"lock:{lock_name}"
        current_holder = await self._client.get(key)

        if current_holder == holder:
            await self._client.delete(key)
            logger.debug(f"Lock released: {lock_name}")
            return True

        logger.warning(f"Cannot release lock {lock_name}: not owner")
        return False

    # Agent state operations
    async def set_agent_status(self, agent_id: str, status: str) -> None:
        """Set agent status in the status hash."""
        await self.hset("agent:status", agent_id, status)

    async def get_agent_status(self, agent_id: str) -> str | None:
        """Get agent status."""
        return await self.hget("agent:status", agent_id)

    async def get_all_agent_statuses(self) -> dict[str, str]:
        """Get all agent statuses."""
        return await self.hgetall("agent:status")

    async def set_task_context(
        self,
        task_id: str,
        context: dict[str, Any],
        expire_seconds: int = 86400,
    ) -> bool:
        """Set task context."""
        key = f"agent:context:{task_id}"
        return await self.set_json(key, context, expire_seconds)

    async def get_task_context(self, task_id: str) -> dict[str, Any] | None:
        """Get task context."""
        key = f"agent:context:{task_id}"
        return await self.get_json(key)
