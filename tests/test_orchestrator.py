"""Tests for Orchestrator class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.core.orchestrator import Orchestrator, Task
from src.core.agent_base import BaseAgent, TaskResult
from src.services.rabbitmq_client import TaskMessage


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    AGENT_TYPE = "mock"
    CAPABILITIES = ["test.action"]

    async def execute_task(self, message: TaskMessage) -> TaskResult:
        return TaskResult(success=True, result={"mock": "result"})


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation(self):
        """Test task creation with defaults."""
        task = Task(
            task_id="task-123",
            title="Test Task",
        )
        assert task.task_id == "task-123"
        assert task.title == "Test Task"
        assert task.status == "pending"
        assert task.priority == "normal"
        assert task.assigned_agent is None
        assert task.tags == []
        assert task.metadata == {}
        assert task.created_at != ""
        assert task.updated_at != ""

    def test_task_with_all_fields(self):
        """Test task creation with all fields."""
        task = Task(
            task_id="task-456",
            title="Full Task",
            description="A task with all fields",
            status="in_progress",
            priority="high",
            assigned_agent="coder",
            parent_task_id="task-123",
            tags=["test", "important"],
            metadata={"key": "value"},
        )
        assert task.task_id == "task-456"
        assert task.description == "A task with all fields"
        assert task.priority == "high"
        assert task.tags == ["test", "important"]
        assert task.metadata == {"key": "value"}

    def test_task_to_dict(self):
        """Test task conversion to dictionary."""
        task = Task(
            task_id="task-789",
            title="Dict Task",
        )
        d = task.to_dict()
        assert d["task_id"] == "task-789"
        assert d["title"] == "Dict Task"
        assert "created_at" in d
        assert "updated_at" in d

    def test_task_from_dict(self):
        """Test task creation from dictionary."""
        data = {
            "task_id": "task-from-dict",
            "title": "From Dict",
            "description": "Created from dict",
            "status": "completed",
            "priority": "low",
            "assigned_agent": "tester",
            "parent_task_id": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "started_at": None,
            "completed_at": None,
            "tags": ["from-dict"],
            "metadata": {},
        }
        task = Task.from_dict(data)
        assert task.task_id == "task-from-dict"
        assert task.title == "From Dict"
        assert task.status == "completed"


class TestOrchestrator:
    """Tests for Orchestrator class."""

    @pytest.fixture
    def orchestrator(self, mock_redis_client, mock_rabbitmq_client):
        """Create orchestrator with mocked dependencies."""
        with patch("src.core.orchestrator.RedisClient", return_value=mock_redis_client), \
             patch("src.core.orchestrator.RabbitMQClient", return_value=mock_rabbitmq_client), \
             patch("src.core.orchestrator.VaultClient") as mock_vault:
            mock_vault.return_value.ping.return_value = True
            orch = Orchestrator()
            orch._redis = mock_redis_client
            orch._rabbitmq = mock_rabbitmq_client
            return orch

    @pytest.mark.asyncio
    async def test_start(self, orchestrator, mock_redis_client, mock_rabbitmq_client):
        """Test orchestrator start."""
        await orchestrator.start()

        mock_redis_client.connect.assert_called_once()
        mock_rabbitmq_client.connect.assert_called_once()
        mock_rabbitmq_client.consume.assert_called_once()
        assert orchestrator._running is True

    @pytest.mark.asyncio
    async def test_stop(self, orchestrator, mock_redis_client, mock_rabbitmq_client):
        """Test orchestrator stop."""
        await orchestrator.start()
        await orchestrator.stop()

        mock_rabbitmq_client.disconnect.assert_called_once()
        mock_redis_client.disconnect.assert_called_once()
        assert orchestrator._running is False

    def test_register_agent_class(self, orchestrator):
        """Test agent class registration."""
        orchestrator.register_agent_class("mock", MockAgent)
        assert "mock" in orchestrator._agent_classes
        assert orchestrator._agent_classes["mock"] == MockAgent

    @pytest.mark.asyncio
    async def test_spawn_agent(self, orchestrator, mock_redis_client, mock_rabbitmq_client):
        """Test agent spawning."""
        orchestrator.register_agent_class("mock", MockAgent)
        await orchestrator.start()

        agent = await orchestrator.spawn_agent("mock")

        assert agent is not None
        assert agent.AGENT_TYPE == "mock"
        assert agent.agent_id in orchestrator._agents

    @pytest.mark.asyncio
    async def test_spawn_unknown_agent(self, orchestrator):
        """Test spawning unknown agent type."""
        await orchestrator.start()

        with pytest.raises(ValueError, match="Unknown agent type"):
            await orchestrator.spawn_agent("unknown")

    @pytest.mark.asyncio
    async def test_create_task(self, orchestrator, mock_redis_client):
        """Test task creation."""
        await orchestrator.start()

        task = await orchestrator.create_task(
            title="Test Task",
            description="A test task",
            priority="high",
            tags=["test"],
        )

        assert task.title == "Test Task"
        assert task.description == "A test task"
        assert task.priority == "high"
        assert task.tags == ["test"]
        assert task.task_id in orchestrator._tasks
        mock_redis_client.set_json.assert_called()

    @pytest.mark.asyncio
    async def test_assign_task(self, orchestrator, mock_redis_client, mock_rabbitmq_client):
        """Test task assignment."""
        await orchestrator.start()

        task = await orchestrator.create_task(
            title="Assign Test",
            description="Task to assign",
        )
        await orchestrator.assign_task(task, "coder")

        assert task.status == "queued"
        assert task.assigned_agent == "coder"
        mock_rabbitmq_client.publish_task.assert_called()

    @pytest.mark.asyncio
    async def test_route_task_coder(self, orchestrator):
        """Test task routing to coder."""
        task = Task(
            task_id="route-1",
            title="Implement new feature",
            description="Code a new login button",
        )
        agent_type = await orchestrator.route_task(task)
        assert agent_type == "coder"

    @pytest.mark.asyncio
    async def test_route_task_architect(self, orchestrator):
        """Test task routing to architect."""
        task = Task(
            task_id="route-2",
            title="Design system architecture",
            description="Review and refactor the module structure",
        )
        agent_type = await orchestrator.route_task(task)
        assert agent_type == "architect"

    @pytest.mark.asyncio
    async def test_route_task_researcher(self, orchestrator):
        """Test task routing to researcher."""
        task = Task(
            task_id="route-3",
            title="Research best practices",
            description="Investigate authentication methods",
        )
        agent_type = await orchestrator.route_task(task)
        assert agent_type == "researcher"

    @pytest.mark.asyncio
    async def test_route_task_tester(self, orchestrator):
        """Test task routing to tester."""
        task = Task(
            task_id="route-4",
            title="Test coverage",
            description="Validate and verify the module",
        )
        agent_type = await orchestrator.route_task(task)
        assert agent_type == "tester"

    @pytest.mark.asyncio
    async def test_route_task_infra(self, orchestrator):
        """Test task routing to infra."""
        task = Task(
            task_id="route-5",
            title="Deploy to production",
            description="Set up kubernetes cluster",
        )
        agent_type = await orchestrator.route_task(task)
        assert agent_type == "infra"

    @pytest.mark.asyncio
    async def test_route_task_default(self, orchestrator):
        """Test default task routing."""
        task = Task(
            task_id="route-6",
            title="Generic task",
            description="Something without keywords",
        )
        agent_type = await orchestrator.route_task(task)
        assert agent_type == "coder"  # Default

    @pytest.mark.asyncio
    async def test_handle_task_complete(self, orchestrator, mock_redis_client):
        """Test handling task completion."""
        await orchestrator.start()

        # Create a task first
        task = await orchestrator.create_task(title="Complete Test")

        # Create completion message
        message = TaskMessage(
            message_id="msg-complete",
            correlation_id="corr-123",
            task_id=task.task_id,
            source_agent="coder",
            target_agent="orchestrator",
            action="task.complete",
            payload={"duration_ms": 1000},
        )

        await orchestrator._handle_task_complete(message)

        assert orchestrator._tasks[task.task_id].status == "completed"
        assert orchestrator._tasks[task.task_id].completed_at is not None

    @pytest.mark.asyncio
    async def test_handle_task_fail(self, orchestrator, mock_redis_client):
        """Test handling task failure."""
        await orchestrator.start()

        # Create a task first
        task = await orchestrator.create_task(title="Fail Test")

        # Create failure message
        message = TaskMessage(
            message_id="msg-fail",
            correlation_id="corr-456",
            task_id=task.task_id,
            source_agent="coder",
            target_agent="orchestrator",
            action="task.fail",
            payload={"error": "Task failed"},
        )

        await orchestrator._handle_task_fail(message)

        assert orchestrator._tasks[task.task_id].status == "failed"

    @pytest.mark.asyncio
    async def test_get_system_health(self, orchestrator, mock_redis_client, mock_rabbitmq_client):
        """Test system health check."""
        await orchestrator.start()

        health = await orchestrator.get_system_health()

        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        assert "components" in health
        assert "redis" in health["components"]
        assert "rabbitmq" in health["components"]
        assert "vault" in health["components"]
        assert "timestamp" in health
