"""
RabbitMQ client for message queue operations.

Provides async interface for publishing and consuming messages.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

import aio_pika
from aio_pika import Message, ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from ..config import get_settings
from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class TaskMessage:
    """Represents a task message."""

    message_id: str
    correlation_id: str
    task_id: str
    source_agent: str
    target_agent: str
    action: str
    payload: dict[str, Any]
    priority: str = "normal"
    timestamp: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "action": self.action,
            "payload": self.payload,
            "priority": self.priority,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskMessage":
        """Create from dictionary."""
        return cls(**data)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, data: str) -> "TaskMessage":
        """Create from JSON string."""
        return cls.from_dict(json.loads(data))


class RabbitMQClient:
    """Async RabbitMQ client wrapper."""

    EXCHANGE_NAME = "agent.tasks"
    DEFAULT_QUEUE = "tasks.default"
    HIGH_PRIORITY_QUEUE = "tasks.high_priority"

    def __init__(self, url: str | None = None):
        """
        Initialize RabbitMQ client.

        Args:
            url: RabbitMQ connection URL. If not provided, uses settings.
        """
        self._url = url or get_settings().rabbitmq.url
        self._connection: aio_pika.Connection | None = None
        self._channel: aio_pika.Channel | None = None
        self._exchange: aio_pika.Exchange | None = None
        self._queues: dict[str, aio_pika.Queue] = {}

    async def connect(self) -> None:
        """Establish connection to RabbitMQ."""
        if self._connection is None:
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()

            # Declare exchange
            self._exchange = await self._channel.declare_exchange(
                self.EXCHANGE_NAME,
                ExchangeType.DIRECT,
                durable=True,
            )

            # Declare queues
            self._queues[self.DEFAULT_QUEUE] = await self._channel.declare_queue(
                self.DEFAULT_QUEUE,
                durable=True,
                arguments={"x-max-priority": 10},
            )
            await self._queues[self.DEFAULT_QUEUE].bind(
                self._exchange,
                routing_key="task.default",
            )

            self._queues[self.HIGH_PRIORITY_QUEUE] = await self._channel.declare_queue(
                self.HIGH_PRIORITY_QUEUE,
                durable=True,
                arguments={"x-max-priority": 10},
            )
            await self._queues[self.HIGH_PRIORITY_QUEUE].bind(
                self._exchange,
                routing_key="task.high",
            )

            logger.info("Connected to RabbitMQ")

    async def disconnect(self) -> None:
        """Close RabbitMQ connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._exchange = None
            self._queues.clear()
            logger.info("Disconnected from RabbitMQ")

    async def ping(self) -> bool:
        """Check if RabbitMQ is available."""
        try:
            if not self._connection:
                await self.connect()
            return self._connection is not None and not self._connection.is_closed
        except Exception as e:
            logger.error(f"RabbitMQ ping failed: {e}")
            return False

    async def publish(
        self,
        message: TaskMessage,
        routing_key: str = "task.default",
    ) -> None:
        """
        Publish a message to the exchange.

        Args:
            message: TaskMessage to publish
            routing_key: Routing key for message delivery
        """
        if not self._exchange:
            await self.connect()

        priority = 5 if message.priority == "normal" else 9

        await self._exchange.publish(
            Message(
                body=message.to_json().encode(),
                content_type="application/json",
                message_id=message.message_id,
                correlation_id=message.correlation_id,
                priority=priority,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

        logger.debug(
            f"Published message {message.message_id} to {routing_key}",
            extra={"task_id": message.task_id},
        )

    async def publish_task(
        self,
        task_id: str,
        action: str,
        payload: dict[str, Any],
        source_agent: str = "orchestrator",
        target_agent: str = "coder",
        priority: str = "normal",
        correlation_id: str | None = None,
    ) -> str:
        """
        Convenience method to publish a task message.

        Returns:
            Message ID
        """
        message = TaskMessage(
            message_id=str(uuid4()),
            correlation_id=correlation_id or str(uuid4()),
            task_id=task_id,
            source_agent=source_agent,
            target_agent=target_agent,
            action=action,
            payload=payload,
            priority=priority,
        )

        routing_key = "task.high" if priority == "high" else "task.default"
        await self.publish(message, routing_key)

        return message.message_id

    async def consume(
        self,
        queue_name: str,
        callback: Callable[[TaskMessage], Any],
        prefetch_count: int = 1,
    ) -> None:
        """
        Start consuming messages from a queue.

        Args:
            queue_name: Name of the queue to consume from
            callback: Async function to handle messages
            prefetch_count: Number of unacked messages to prefetch
        """
        if not self._channel:
            await self.connect()

        await self._channel.set_qos(prefetch_count=prefetch_count)

        queue = self._queues.get(queue_name)
        if not queue:
            raise ValueError(f"Unknown queue: {queue_name}")

        async def process_message(message: AbstractIncomingMessage) -> None:
            async with message.process():
                try:
                    task_message = TaskMessage.from_json(message.body.decode())
                    logger.debug(
                        f"Received message {task_message.message_id}",
                        extra={"task_id": task_message.task_id},
                    )
                    await callback(task_message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    raise

        await queue.consume(process_message)
        logger.info(f"Started consuming from {queue_name}")

    async def get_queue_depth(self, queue_name: str) -> int:
        """Get the number of messages in a queue."""
        if not self._channel:
            await self.connect()

        queue = self._queues.get(queue_name)
        if queue:
            return queue.declaration_result.message_count
        return 0
