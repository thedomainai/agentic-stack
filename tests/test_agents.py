"""Tests for specialized agents."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents import (
    ArchitectAgent,
    CoderAgent,
    InfraAgent,
    ResearcherAgent,
    TesterAgent,
)
from src.services.rabbitmq_client import TaskMessage


class TestCoderAgent:
    """Tests for CoderAgent."""

    @pytest.fixture
    def coder_agent(self, mock_redis_client, mock_rabbitmq_client):
        """Create coder agent for testing."""
        agent = CoderAgent(
            agent_id="coder-test-001",
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )
        return agent

    def test_agent_type(self, coder_agent):
        """Test agent type is correct."""
        assert coder_agent.AGENT_TYPE == "coder"

    def test_capabilities(self, coder_agent):
        """Test agent capabilities."""
        expected = [
            "task.assign",
            "code.generate",
            "code.fix",
            "code.refactor",
            "code.document",
        ]
        assert coder_agent.CAPABILITIES == expected

    def test_can_handle(self, coder_agent):
        """Test capability checking."""
        assert coder_agent.can_handle("code.generate") is True
        assert coder_agent.can_handle("code.fix") is True
        assert coder_agent.can_handle("unknown.action") is False

    @pytest.mark.asyncio
    async def test_execute_unknown_action(
        self, coder_agent, mock_redis_client, mock_rabbitmq_client
    ):
        """Test executing unknown action."""
        await coder_agent.start()

        message = TaskMessage(
            message_id="msg-001",
            correlation_id="corr-001",
            task_id="task-001",
            source_agent="orchestrator",
            target_agent="coder",
            action="unknown.action",
            payload={},
        )

        result = await coder_agent.execute_task(message)
        assert result.success is False
        assert "Unknown action" in result.error


class TestArchitectAgent:
    """Tests for ArchitectAgent."""

    @pytest.fixture
    def architect_agent(self, mock_redis_client, mock_rabbitmq_client):
        """Create architect agent for testing."""
        return ArchitectAgent(
            agent_id="architect-test-001",
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )

    def test_agent_type(self, architect_agent):
        """Test agent type is correct."""
        assert architect_agent.AGENT_TYPE == "architect"

    def test_capabilities(self, architect_agent):
        """Test agent capabilities."""
        expected = [
            "task.assign",
            "design.review",
            "design.create",
            "code.review",
            "refactor.recommend",
            "decision.analyze",
        ]
        assert architect_agent.CAPABILITIES == expected


class TestResearcherAgent:
    """Tests for ResearcherAgent."""

    @pytest.fixture
    def researcher_agent(self, mock_redis_client, mock_rabbitmq_client):
        """Create researcher agent for testing."""
        return ResearcherAgent(
            agent_id="researcher-test-001",
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )

    def test_agent_type(self, researcher_agent):
        """Test agent type is correct."""
        assert researcher_agent.AGENT_TYPE == "researcher"

    def test_capabilities(self, researcher_agent):
        """Test agent capabilities."""
        expected = [
            "task.assign",
            "research.search",
            "research.analyze",
            "research.summarize",
            "research.compare",
            "docs.search",
        ]
        assert researcher_agent.CAPABILITIES == expected


class TestTesterAgent:
    """Tests for TesterAgent."""

    @pytest.fixture
    def tester_agent(self, mock_redis_client, mock_rabbitmq_client):
        """Create tester agent for testing."""
        return TesterAgent(
            agent_id="tester-test-001",
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )

    def test_agent_type(self, tester_agent):
        """Test agent type is correct."""
        assert tester_agent.AGENT_TYPE == "tester"

    def test_capabilities(self, tester_agent):
        """Test agent capabilities."""
        expected = [
            "task.assign",
            "test.generate",
            "test.execute",
            "test.coverage",
            "test.validate",
            "bug.reproduce",
        ]
        assert tester_agent.CAPABILITIES == expected


class TestInfraAgent:
    """Tests for InfraAgent."""

    @pytest.fixture
    def infra_agent(self, mock_redis_client, mock_rabbitmq_client):
        """Create infra agent for testing."""
        return InfraAgent(
            agent_id="infra-test-001",
            redis_client=mock_redis_client,
            rabbitmq_client=mock_rabbitmq_client,
        )

    def test_agent_type(self, infra_agent):
        """Test agent type is correct."""
        assert infra_agent.AGENT_TYPE == "infra"

    def test_capabilities(self, infra_agent):
        """Test agent capabilities."""
        expected = [
            "task.assign",
            "infra.deploy",
            "infra.provision",
            "infra.monitor",
            "docker.manage",
            "k8s.manage",
            "cicd.configure",
        ]
        assert infra_agent.CAPABILITIES == expected


class TestAgentLLMIntegration:
    """Tests for agent LLM integration."""

    @pytest.fixture
    def mock_anthropic(self, mock_anthropic_response):
        """Create mock Anthropic client."""
        with patch("anthropic.AsyncAnthropic") as mock_class:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
            mock_class.return_value = mock_client
            yield mock_client

    @pytest.mark.asyncio
    async def test_coder_generate_code(
        self,
        mock_redis_client,
        mock_rabbitmq_client,
        mock_anthropic,
        mock_settings,
    ):
        """Test code generation with mocked LLM."""
        with patch("src.agents.coder.get_settings", return_value=mock_settings):
            agent = CoderAgent(
                redis_client=mock_redis_client,
                rabbitmq_client=mock_rabbitmq_client,
            )
            agent._anthropic = mock_anthropic

            await agent.start()

            message = TaskMessage(
                message_id="msg-gen",
                correlation_id="corr-gen",
                task_id="task-gen",
                source_agent="orchestrator",
                target_agent="coder",
                action="code.generate",
                payload={
                    "specification": "Create a hello world function",
                    "language": "python",
                },
            )

            result = await agent.execute_task(message)

            assert result.success is True
            assert "code" in result.result
            mock_anthropic.messages.create.assert_called_once()
