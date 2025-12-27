"""
Central orchestrator for coordinating AI agents.

The orchestrator manages task routing, agent coordination,
and overall system state.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Type
from uuid import uuid4

from ..config import get_settings
from ..services import RedisClient, RabbitMQClient, VaultClient
from ..services.rabbitmq_client import TaskMessage
from ..utils import get_logger
from .agent_base import BaseAgent, AgentStatus, TaskResult

logger = get_logger(__name__, agent_id="orchestrator")


@dataclass
class Task:
    """Represents a task in the system."""

    task_id: str
    title: str
    description: str = ""
    status: str = "pending"
    priority: str = "normal"
    assigned_agent: str | None = None
    parent_task_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        now = datetime.utcnow().isoformat() + "Z"
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "assigned_agent": self.assigned_agent,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create from dictionary."""
        return cls(**data)


class Orchestrator:
    """
    Central orchestrator that coordinates all agents.

    Responsibilities:
    - Task decomposition and delegation
    - Agent coordination and communication
    - Global state management
    - Decision logging
    - Failure detection and recovery
    """

    def __init__(self):
        """Initialize the orchestrator."""
        self._settings = get_settings()

        # Service clients
        self._redis = RedisClient()
        self._rabbitmq = RabbitMQClient()
        self._vault = VaultClient()

        # Agent registry
        self._agents: dict[str, BaseAgent] = {}
        self._agent_classes: dict[str, Type[BaseAgent]] = {}

        # State
        self._running = False
        self._tasks: dict[str, Task] = {}

    async def start(self) -> None:
        """Start the orchestrator."""
        logger.info("Starting orchestrator")

        # Connect to services
        await self._redis.connect()
        await self._rabbitmq.connect()

        # Verify Vault connectivity
        if not self._vault.ping():
            logger.warning("Vault is not accessible - secrets will not be available")

        # Set orchestrator status
        await self._redis.set_agent_status("orchestrator", AgentStatus.IDLE.value)

        self._running = True

        # Start consuming messages
        await self._rabbitmq.consume(
            RabbitMQClient.DEFAULT_QUEUE,
            self._handle_message,
        )

        logger.info("Orchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        logger.info("Stopping orchestrator")

        self._running = False

        # Stop all managed agents
        for agent in self._agents.values():
            await agent.stop()

        # Update status
        await self._redis.set_agent_status("orchestrator", AgentStatus.OFFLINE.value)

        # Disconnect from services
        await self._rabbitmq.disconnect()
        await self._redis.disconnect()

        logger.info("Orchestrator stopped")

    def register_agent_class(
        self,
        agent_type: str,
        agent_class: Type[BaseAgent],
    ) -> None:
        """
        Register an agent class for instantiation.

        Args:
            agent_type: Type identifier (e.g., "coder", "researcher")
            agent_class: The agent class to register
        """
        self._agent_classes[agent_type] = agent_class
        logger.info(f"Registered agent class: {agent_type}")

    async def spawn_agent(self, agent_type: str) -> BaseAgent:
        """
        Spawn a new agent instance.

        Args:
            agent_type: Type of agent to spawn

        Returns:
            The spawned agent instance
        """
        if agent_type not in self._agent_classes:
            raise ValueError(f"Unknown agent type: {agent_type}")

        agent_class = self._agent_classes[agent_type]
        agent = agent_class(
            redis_client=self._redis,
            rabbitmq_client=self._rabbitmq,
        )

        await agent.start()
        self._agents[agent.agent_id] = agent

        logger.info(f"Spawned agent: {agent.agent_id}")
        return agent

    async def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """
        Create a new task.

        Args:
            title: Task title
            description: Task description
            priority: Task priority (low, normal, high, critical)
            tags: Optional tags
            metadata: Optional metadata

        Returns:
            The created Task
        """
        task = Task(
            task_id=str(uuid4()),
            title=title,
            description=description,
            priority=priority,
            tags=tags,
            metadata=metadata,
        )

        # Store task
        self._tasks[task.task_id] = task
        await self._redis.set_json(f"task:{task.task_id}", task.to_dict())

        # Log decision
        await self._log_decision(
            decision_type="task_creation",
            context=f"Created task: {title}",
            chosen_option="create",
            rationale="New task submitted",
            task_id=task.task_id,
        )

        logger.info(f"Created task {task.task_id}: {title}")
        return task

    async def assign_task(self, task: Task, agent_type: str) -> None:
        """
        Assign a task to an agent type.

        Args:
            task: The task to assign
            agent_type: Type of agent to assign to
        """
        # Update task status
        task.status = "queued"
        task.assigned_agent = agent_type
        task.updated_at = datetime.utcnow().isoformat() + "Z"

        await self._redis.set_json(f"task:{task.task_id}", task.to_dict())

        # Publish to queue
        routing_key = "task.high" if task.priority in ("high", "critical") else "task.default"

        await self._rabbitmq.publish_task(
            task_id=task.task_id,
            action="task.assign",
            payload={
                "title": task.title,
                "description": task.description,
                "tags": task.tags,
                "metadata": task.metadata,
            },
            source_agent="orchestrator",
            target_agent=agent_type,
            priority=task.priority,
        )

        # Log decision
        await self._log_decision(
            decision_type="task_delegation",
            context=f"Assigning task to agent",
            options_considered=[
                {"option": agent_type, "rationale": "Best match for task type"},
            ],
            chosen_option=agent_type,
            rationale=f"Delegating based on task requirements",
            task_id=task.task_id,
        )

        logger.info(f"Assigned task {task.task_id} to {agent_type}")

    async def route_task(self, task: Task) -> str:
        """
        Determine which agent type should handle a task.

        Args:
            task: The task to route

        Returns:
            The agent type to handle the task
        """
        title_lower = task.title.lower()
        description_lower = task.description.lower()
        combined = f"{title_lower} {description_lower}"

        # Simple keyword-based routing
        routing_rules = [
            (["architecture", "design", "review", "refactor"], "architect"),
            (["implement", "code", "fix", "bug", "feature"], "coder"),
            (["research", "search", "find", "investigate"], "researcher"),
            (["test", "validate", "verify", "coverage"], "tester"),
            (["deploy", "infrastructure", "docker", "kubernetes"], "infra"),
        ]

        for keywords, agent_type in routing_rules:
            if any(kw in combined for kw in keywords):
                return agent_type

        # Default to coder
        return "coder"

    async def _handle_message(self, message: TaskMessage) -> None:
        """Handle incoming messages."""
        logger.debug(f"Handling message: {message.action}")

        if message.action == "task.complete":
            await self._handle_task_complete(message)
        elif message.action == "task.fail":
            await self._handle_task_fail(message)
        elif message.action == "task.progress":
            await self._handle_task_progress(message)
        else:
            logger.warning(f"Unknown action: {message.action}")

    async def _handle_task_complete(self, message: TaskMessage) -> None:
        """Handle task completion."""
        task_id = message.task_id

        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.status = "completed"
            task.completed_at = datetime.utcnow().isoformat() + "Z"
            task.updated_at = task.completed_at

            await self._redis.set_json(f"task:{task_id}", task.to_dict())

        # Log metrics
        await self._log_velocity_metric(message)

        logger.info(f"Task {task_id} completed by {message.source_agent}")

    async def _handle_task_fail(self, message: TaskMessage) -> None:
        """Handle task failure."""
        task_id = message.task_id

        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.status = "failed"
            task.updated_at = datetime.utcnow().isoformat() + "Z"

            await self._redis.set_json(f"task:{task_id}", task.to_dict())

        error = message.payload.get("error", "Unknown error")
        logger.error(f"Task {task_id} failed: {error}")

        # Could implement retry logic here

    async def _handle_task_progress(self, message: TaskMessage) -> None:
        """Handle task progress update."""
        task_id = message.task_id
        progress = message.payload.get("progress", 0)

        # Update context
        context = await self._redis.get_task_context(task_id)
        if context:
            context["progress"] = progress
            context["last_update"] = datetime.utcnow().isoformat()
            await self._redis.set_task_context(task_id, context)

        logger.debug(f"Task {task_id} progress: {progress}%")

    async def _log_decision(
        self,
        decision_type: str,
        context: str,
        chosen_option: str,
        rationale: str,
        task_id: str | None = None,
        options_considered: list[dict[str, Any]] | None = None,
    ) -> None:
        """Log a decision to the decisions JSONL file."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision_id": str(uuid4()),
            "agent": "orchestrator",
            "task_id": task_id,
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

    async def _log_velocity_metric(self, message: TaskMessage) -> None:
        """Log velocity metric for completed task."""
        duration_ms = message.payload.get("duration_ms", 0)

        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "task_id": message.task_id,
            "agent": message.source_agent,
            "duration_ms": duration_ms,
            "success": message.action == "task.complete",
        }

        filepath = self._settings.metrics_dir / "VELOCITY.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def get_system_health(self) -> dict[str, Any]:
        """Get overall system health status."""
        health = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "components": {},
        }

        # Check Redis
        try:
            redis_ok = await self._redis.ping()
            health["components"]["redis"] = {
                "status": "healthy" if redis_ok else "unhealthy",
            }
        except Exception as e:
            health["components"]["redis"] = {"status": "error", "error": str(e)}
            health["status"] = "unhealthy"

        # Check RabbitMQ
        try:
            rabbitmq_ok = await self._rabbitmq.ping()
            health["components"]["rabbitmq"] = {
                "status": "healthy" if rabbitmq_ok else "unhealthy",
            }
        except Exception as e:
            health["components"]["rabbitmq"] = {"status": "error", "error": str(e)}
            health["status"] = "unhealthy"

        # Check Vault
        try:
            vault_ok = self._vault.ping()
            health["components"]["vault"] = {
                "status": "healthy" if vault_ok else "unhealthy",
            }
        except Exception as e:
            health["components"]["vault"] = {"status": "error", "error": str(e)}
            # Vault being down is not critical
            if health["status"] == "healthy":
                health["status"] = "degraded"

        # Agent statuses
        agent_statuses = await self._redis.get_all_agent_statuses()
        health["agents"] = agent_statuses

        return health
