"""
Base agent class for all specialized agents.

Provides common functionality for agent lifecycle, task handling,
and communication with the orchestrator.
"""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..config import get_settings
from ..services import RedisClient, RabbitMQClient
from ..services.rabbitmq_client import TaskMessage
from ..utils import get_logger


class AgentStatus(str, Enum):
    """Agent status enumeration."""

    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


@dataclass
class TaskResult:
    """Result of a task execution."""

    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = 0
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "artifacts": self.artifacts,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Provides:
    - Agent lifecycle management (start, stop, heartbeat)
    - Task queue consumption
    - Status reporting
    - Decision logging
    """

    # Agent type identifier (override in subclasses)
    AGENT_TYPE: str = "base"

    # Capabilities this agent provides (override in subclasses)
    CAPABILITIES: list[str] = []

    def __init__(
        self,
        agent_id: str | None = None,
        redis_client: RedisClient | None = None,
        rabbitmq_client: RabbitMQClient | None = None,
    ):
        """
        Initialize the agent.

        Args:
            agent_id: Unique identifier for this agent instance
            redis_client: Optional Redis client (creates new if not provided)
            rabbitmq_client: Optional RabbitMQ client (creates new if not provided)
        """
        self.agent_id = agent_id or f"{self.AGENT_TYPE}-{uuid4().hex[:8]}"
        self.logger = get_logger(__name__, agent_id=self.agent_id)

        self._redis = redis_client or RedisClient()
        self._rabbitmq = rabbitmq_client or RabbitMQClient()

        self._status = AgentStatus.OFFLINE
        self._current_task_id: str | None = None
        self._started_at: datetime | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

        self._settings = get_settings()

    @property
    def status(self) -> AgentStatus:
        """Get current agent status."""
        return self._status

    @property
    def is_busy(self) -> bool:
        """Check if agent is currently processing a task."""
        return self._status == AgentStatus.BUSY

    async def start(self) -> None:
        """Start the agent."""
        self.logger.info(f"Starting agent {self.agent_id}")

        # Connect to services
        await self._redis.connect()
        await self._rabbitmq.connect()

        # Set initial status
        self._status = AgentStatus.IDLE
        self._started_at = datetime.utcnow()
        self._running = True

        await self._update_status()

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        self.logger.info(f"Agent {self.agent_id} started")

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        self.logger.info(f"Stopping agent {self.agent_id}")

        self._running = False

        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Update status
        self._status = AgentStatus.OFFLINE
        await self._update_status()

        # Disconnect from services
        await self._rabbitmq.disconnect()
        await self._redis.disconnect()

        self.logger.info(f"Agent {self.agent_id} stopped")

    async def _update_status(self) -> None:
        """Update agent status in Redis."""
        await self._redis.set_agent_status(self.agent_id, self._status.value)

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to indicate agent is alive."""
        interval = self._settings.heartbeat_interval_seconds

        while self._running:
            try:
                await self._update_status()
                self.logger.debug(f"Heartbeat: {self._status.value}")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(interval)

    async def handle_message(self, message: TaskMessage) -> None:
        """
        Handle an incoming task message.

        Args:
            message: The task message to handle
        """
        self.logger.info(
            f"Received task {message.task_id}: {message.action}",
            extra={"task_id": message.task_id},
        )

        # Update status
        self._status = AgentStatus.BUSY
        self._current_task_id = message.task_id
        await self._update_status()

        # Store task context
        await self._redis.set_task_context(
            message.task_id,
            {
                "assigned_agent": self.agent_id,
                "started_at": datetime.utcnow().isoformat(),
                "action": message.action,
                "status": "in_progress",
            },
        )

        start_time = datetime.utcnow()

        try:
            # Execute the task
            result = await self.execute_task(message)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result.duration_ms = duration_ms

            # Send result
            await self._send_result(message, result)

        except Exception as e:
            self.logger.exception(f"Task execution failed: {e}")
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Send error result
            await self._send_result(
                message,
                TaskResult(
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                ),
            )

            # Log failure
            await self._log_failure(message, str(e))

        finally:
            # Reset status
            self._status = AgentStatus.IDLE
            self._current_task_id = None
            await self._update_status()

    async def _send_result(
        self,
        original_message: TaskMessage,
        result: TaskResult,
    ) -> None:
        """Send task result back to orchestrator."""
        action = "task.complete" if result.success else "task.fail"

        await self._rabbitmq.publish_task(
            task_id=original_message.task_id,
            action=action,
            payload=result.to_dict(),
            source_agent=self.agent_id,
            target_agent="orchestrator",
            correlation_id=original_message.correlation_id,
        )

    async def _log_decision(
        self,
        decision_type: str,
        context: str,
        options_considered: list[dict[str, Any]] | None,
        chosen_option: str,
        rationale: str,
        task_id: str | None = None,
    ) -> None:
        """Log a decision to the decisions JSONL file."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision_id": str(uuid4()),
            "agent": self.agent_id,
            "task_id": task_id or self._current_task_id,
            "decision_type": decision_type,
            "context": context,
            "options_considered": options_considered or [],
            "chosen_option": chosen_option,
            "rationale": rationale,
            "outcome": "pending",
        }

        filepath = self._settings.memory_dir / "DECISIONS.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def _log_failure(
        self,
        message: TaskMessage,
        error: str,
        severity: str = "error",
    ) -> None:
        """Log a failure to the failures JSONL file."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "failure_id": str(uuid4()),
            "agent": self.agent_id,
            "task_id": message.task_id,
            "severity": severity,
            "category": "execution_error",
            "message": error,
            "context": {
                "action": message.action,
                "payload_keys": list(message.payload.keys()),
            },
            "resolved": False,
        }

        filepath = self._settings.memory_dir / "FAILURES.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def _log_discovery(
        self,
        category: str,
        title: str,
        description: str,
        evidence: list[str] | None = None,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> None:
        """Log a discovery to the discoveries JSONL file."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "discovery_id": str(uuid4()),
            "agent": self.agent_id,
            "task_id": self._current_task_id,
            "category": category,
            "title": title,
            "description": description,
            "evidence": evidence or [],
            "confidence": confidence,
            "tags": tags or [],
        }

        filepath = self._settings.memory_dir / "DISCOVERIES.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    @abstractmethod
    async def execute_task(self, message: TaskMessage) -> TaskResult:
        """
        Execute a task. Must be implemented by subclasses.

        Args:
            message: The task message containing action and payload

        Returns:
            TaskResult with success status and result/error
        """
        pass

    def can_handle(self, action: str) -> bool:
        """
        Check if this agent can handle a specific action.

        Args:
            action: The action to check

        Returns:
            True if this agent can handle the action
        """
        return action in self.CAPABILITIES
