"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings, RedisConfig, RabbitMQConfig, VaultConfig, LLMConfig
from src.services import RedisClient, RabbitMQClient
from src.services.rabbitmq_client import TaskMessage


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        environment="test",
        redis=RedisConfig(host="localhost", port=6379),
        rabbitmq=RabbitMQConfig(host="localhost", port=5672),
        vault=VaultConfig(url="http://localhost:8200"),
        llm=LLMConfig(api_key="test-api-key", model="claude-sonnet-4-20250514"),
    )


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create mock Redis client."""
    client = AsyncMock(spec=RedisClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    client.get_json = AsyncMock(return_value=None)
    client.set_json = AsyncMock(return_value=True)
    client.set_agent_status = AsyncMock()
    client.get_agent_status = AsyncMock(return_value="idle")
    client.get_all_agent_statuses = AsyncMock(return_value={})
    client.set_task_context = AsyncMock(return_value=True)
    client.get_task_context = AsyncMock(return_value=None)
    client.acquire_lock = AsyncMock(return_value=True)
    client.release_lock = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_rabbitmq_client() -> AsyncMock:
    """Create mock RabbitMQ client."""
    client = AsyncMock(spec=RabbitMQClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.publish_task = AsyncMock()
    client.consume = AsyncMock()
    return client


@pytest.fixture
def sample_task_message() -> TaskMessage:
    """Create sample task message for testing."""
    return TaskMessage(
        message_id="msg-123",
        correlation_id="corr-123",
        task_id="task-123",
        source_agent="orchestrator",
        target_agent="coder",
        action="code.generate",
        payload={
            "specification": "Create a hello world function",
            "language": "python",
        },
        priority="normal",
    )


@pytest.fixture
def mock_anthropic_response() -> MagicMock:
    """Create mock Anthropic API response."""
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = "Generated response from LLM"
    response.content = [content_block]
    return response
