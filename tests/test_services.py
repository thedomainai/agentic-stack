"""Tests for service clients."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.services.rabbitmq_client import TaskMessage, RabbitMQClient
from src.services.redis_client import RedisClient


class TestTaskMessage:
    """Tests for TaskMessage dataclass."""

    def test_create_task_message(self):
        """Test creating a task message."""
        message = TaskMessage(
            message_id="msg-001",
            correlation_id="corr-001",
            task_id="task-001",
            source_agent="orchestrator",
            target_agent="coder",
            action="code.generate",
            payload={"spec": "test"},
        )
        assert message.message_id == "msg-001"
        assert message.priority == "normal"  # Default
        assert message.payload == {"spec": "test"}

    def test_task_message_to_json(self):
        """Test converting task message to JSON."""
        message = TaskMessage(
            message_id="msg-002",
            correlation_id="corr-002",
            task_id="task-002",
            source_agent="orchestrator",
            target_agent="tester",
            action="test.run",
            payload={"tests": ["test1", "test2"]},
            priority="high",
        )
        json_str = message.to_json()
        data = json.loads(json_str)

        assert data["message_id"] == "msg-002"
        assert data["action"] == "test.run"
        assert data["priority"] == "high"
        assert data["payload"]["tests"] == ["test1", "test2"]

    def test_task_message_from_json(self):
        """Test creating task message from JSON."""
        json_str = json.dumps({
            "message_id": "msg-003",
            "correlation_id": "corr-003",
            "task_id": "task-003",
            "source_agent": "coder",
            "target_agent": "orchestrator",
            "action": "task.complete",
            "payload": {"result": "success"},
            "priority": "normal",
        })
        message = TaskMessage.from_json(json_str)

        assert message.message_id == "msg-003"
        assert message.action == "task.complete"
        assert message.payload["result"] == "success"


class TestRedisClient:
    """Tests for RedisClient."""

    @pytest.fixture
    def redis_client(self):
        """Create Redis client with mocked connection."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._connected = True
        return client

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test Redis connection."""
        with patch("src.services.redis_client.redis.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_from_url.return_value = mock_redis

            client = RedisClient()
            await client.connect()

            mock_from_url.assert_called_once()
            mock_redis.ping.assert_called_once()
            assert client._connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, redis_client):
        """Test Redis disconnection."""
        await redis_client.disconnect()

        redis_client._redis.close.assert_called_once()
        assert redis_client._connected is False

    @pytest.mark.asyncio
    async def test_ping(self, redis_client):
        """Test Redis ping."""
        redis_client._redis.ping = AsyncMock(return_value=True)
        result = await redis_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_get(self, redis_client):
        """Test Redis get."""
        redis_client._redis.get = AsyncMock(return_value=b"test_value")
        result = await redis_client.get("test_key")
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_none(self, redis_client):
        """Test Redis get with no value."""
        redis_client._redis.get = AsyncMock(return_value=None)
        result = await redis_client.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set(self, redis_client):
        """Test Redis set."""
        redis_client._redis.set = AsyncMock(return_value=True)
        result = await redis_client.set("key", "value")
        assert result is True
        redis_client._redis.set.assert_called_with("key", "value", ex=None)

    @pytest.mark.asyncio
    async def test_set_with_expiry(self, redis_client):
        """Test Redis set with expiry."""
        redis_client._redis.set = AsyncMock(return_value=True)
        result = await redis_client.set("key", "value", expire_seconds=3600)
        assert result is True
        redis_client._redis.set.assert_called_with("key", "value", ex=3600)

    @pytest.mark.asyncio
    async def test_delete(self, redis_client):
        """Test Redis delete."""
        redis_client._redis.delete = AsyncMock(return_value=1)
        result = await redis_client.delete("key")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_json(self, redis_client):
        """Test getting JSON value."""
        redis_client._redis.get = AsyncMock(return_value=b'{"key": "value"}')
        result = await redis_client.get_json("json_key")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_set_json(self, redis_client):
        """Test setting JSON value."""
        redis_client._redis.set = AsyncMock(return_value=True)
        result = await redis_client.set_json("json_key", {"key": "value"})
        assert result is True
        redis_client._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_agent_status(self, redis_client):
        """Test setting agent status."""
        redis_client._redis.hset = AsyncMock()
        redis_client._redis.expire = AsyncMock()

        await redis_client.set_agent_status("agent-001", "busy")

        redis_client._redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_get_agent_status(self, redis_client):
        """Test getting agent status."""
        redis_client._redis.hget = AsyncMock(return_value=b"idle")
        result = await redis_client.get_agent_status("agent-001")
        assert result == "idle"

    @pytest.mark.asyncio
    async def test_acquire_lock(self, redis_client):
        """Test acquiring a lock."""
        redis_client._redis.set = AsyncMock(return_value=True)
        result = await redis_client.acquire_lock("test_lock", "holder_1")
        assert result is True
        redis_client._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_lock(self, redis_client):
        """Test releasing a lock."""
        redis_client._redis.get = AsyncMock(return_value=b"holder_1")
        redis_client._redis.delete = AsyncMock(return_value=1)

        result = await redis_client.release_lock("test_lock", "holder_1")
        assert result is True

    @pytest.mark.asyncio
    async def test_release_lock_wrong_holder(self, redis_client):
        """Test releasing lock with wrong holder."""
        redis_client._redis.get = AsyncMock(return_value=b"holder_2")

        result = await redis_client.release_lock("test_lock", "holder_1")
        assert result is False


class TestRabbitMQClient:
    """Tests for RabbitMQClient."""

    @pytest.fixture
    def rabbitmq_client(self):
        """Create RabbitMQ client with mocked connection."""
        client = RabbitMQClient()
        client._connection = AsyncMock()
        client._channel = AsyncMock()
        client._exchange = AsyncMock()
        client._connected = True
        return client

    @pytest.mark.asyncio
    async def test_publish_task(self, rabbitmq_client):
        """Test publishing a task message."""
        rabbitmq_client._exchange.publish = AsyncMock()

        await rabbitmq_client.publish_task(
            task_id="task-001",
            action="code.generate",
            payload={"spec": "test"},
            source_agent="orchestrator",
            target_agent="coder",
        )

        rabbitmq_client._exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_task_high_priority(self, rabbitmq_client):
        """Test publishing high priority task."""
        rabbitmq_client._exchange.publish = AsyncMock()

        await rabbitmq_client.publish_task(
            task_id="task-002",
            action="urgent.task",
            payload={},
            source_agent="orchestrator",
            target_agent="coder",
            priority="high",
        )

        rabbitmq_client._exchange.publish.assert_called_once()
        # Verify routing key includes priority
        call_args = rabbitmq_client._exchange.publish.call_args
        assert "task.high" in str(call_args)

    @pytest.mark.asyncio
    async def test_ping(self, rabbitmq_client):
        """Test RabbitMQ ping."""
        rabbitmq_client._connection.is_closed = False
        result = await rabbitmq_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_disconnected(self, rabbitmq_client):
        """Test RabbitMQ ping when disconnected."""
        rabbitmq_client._connected = False
        result = await rabbitmq_client.ping()
        assert result is False
