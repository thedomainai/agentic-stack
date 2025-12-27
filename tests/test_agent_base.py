"""Tests for BaseAgent class."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from src.core.agent_base import BaseAgent, AgentStatus, TaskResult
from src.services.rabbitmq_client import TaskMessage


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    AGENT_TYPE = "test"
    CAPABILITIES = ["test.action", "test.other"]

    async def execute_task(self, message: TaskMessage) -> TaskResult:
        """Execute a test task."""
        if message.action == "test.action":
            return TaskResult(
                success=True,
                result={"data": "test result"},
            )
        elif message.action == "test.fail":
            return TaskResult(
                success=False,
                error="Test failure",
            )
        elif message.action == "test.error":
            raise RuntimeError("Test exception")
        else:
            return TaskResult(
                success=False,
                error=f"Unknown action: {message.action}",
            )


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.ERROR.value == "error"
        assert AgentStatus.OFFLINE.value == "offline"
        assert AgentStatus.MAINTENANCE.value == "maintenance"


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_success_result(self):
        """Test successful task result."""
        result = TaskResult(
            success=True,
            result={"key": "value"},
        )
        assert result.success is True
        assert result.result == {"key": "value"}
        assert result.error is None
        assert result.duration_ms == 0
        assert result.artifacts == []

    def test_failure_result(self):
        """Test failed task result."""
        result = TaskResult(
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.result is None
        assert result.error == "Something went wrong"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = TaskResult(
            success=True,
            result={"data": "test"},
            duration_ms=100,
            artifacts=[{"name": "artifact1"}],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["result"] == {"data": "test"}
        assert d["error"] is None
        assert d["duration_ms"] == 100
        assert d["artifacts"] == [{"name": "artifact1"}]


class TestBaseAgent:
    """Tests for BaseAgent class."""

    @pytest.fixture
    def agent(self, mock_redis_client, mock_rabbitmq_client):
        """Create a concrete agent for testing."""
        return ConcreteAgent(
            agent_id="test-agent-001",
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )

    def test_initialization(self, agent):
        """Test agent initialization."""
        assert agent.agent_id == "test-agent-001"
        assert agent.AGENT_TYPE == "test"
        assert agent.status == AgentStatus.OFFLINE
        assert agent.is_busy is False

    def test_auto_generated_id(self, mock_redis_client, mock_rabbitmq_client):
        """Test agent with auto-generated ID."""
        agent = ConcreteAgent(
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )
        assert agent.agent_id.startswith("test-")
        assert len(agent.agent_id) > 5

    @pytest.mark.asyncio
    async def test_start(self, agent, mock_redis_client, mock_rabbitmq_client):
        """Test agent start."""
        await agent.start()

        mock_redis_client.connect.assert_called_once()
        mock_rabbitmq_client.connect.assert_called_once()
        assert agent.status == AgentStatus.IDLE
        mock_redis_client.set_agent_status.assert_called()

    @pytest.mark.asyncio
    async def test_stop(self, agent, mock_redis_client, mock_rabbitmq_client):
        """Test agent stop."""
        await agent.start()
        await agent.stop()

        assert agent.status == AgentStatus.OFFLINE
        mock_rabbitmq_client.disconnect.assert_called_once()
        mock_redis_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_success(
        self, agent, mock_redis_client, mock_rabbitmq_client, sample_task_message
    ):
        """Test successful message handling."""
        sample_task_message.action = "test.action"

        await agent.start()
        await agent.handle_message(sample_task_message)

        # Verify status changes
        assert agent.status == AgentStatus.IDLE

        # Verify result was published
        mock_rabbitmq_client.publish_task.assert_called()
        call_args = mock_rabbitmq_client.publish_task.call_args
        assert call_args.kwargs["action"] == "task.complete"

    @pytest.mark.asyncio
    async def test_handle_message_failure(
        self, agent, mock_redis_client, mock_rabbitmq_client, sample_task_message
    ):
        """Test failed message handling."""
        sample_task_message.action = "test.fail"

        await agent.start()
        await agent.handle_message(sample_task_message)

        # Verify failure was published
        mock_rabbitmq_client.publish_task.assert_called()
        call_args = mock_rabbitmq_client.publish_task.call_args
        assert call_args.kwargs["action"] == "task.fail"

    @pytest.mark.asyncio
    async def test_handle_message_exception(
        self, agent, mock_redis_client, mock_rabbitmq_client, sample_task_message
    ):
        """Test message handling with exception."""
        sample_task_message.action = "test.error"

        await agent.start()
        await agent.handle_message(sample_task_message)

        # Verify error was published
        mock_rabbitmq_client.publish_task.assert_called()
        call_args = mock_rabbitmq_client.publish_task.call_args
        assert call_args.kwargs["action"] == "task.fail"

    def test_can_handle(self, agent):
        """Test capability checking."""
        assert agent.can_handle("test.action") is True
        assert agent.can_handle("test.other") is True
        assert agent.can_handle("unknown.action") is False
