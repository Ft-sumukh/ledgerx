"""
LEDGER-ORBIT: Queue Abstraction
================================
Defines the abstract Queue interface and message data structures.

DESIGN DECISIONS:
  - The Queue interface is broker-agnostic. The same interface is implemented by
    InMemoryQueue (development/testing), RedisQueue (staging), and could support
    SQS, RabbitMQ, or Kafka adapters without changing business logic.
  - QueueMessage uses a visibility_timeout model (inspired by SQS) — messages
    remain in the queue until ack'd, allowing crash recovery. If a worker crashes
    before ack, the message re-appears after the timeout.
  - receive_count tracks delivery attempts; messages exceeding max_receive_count
    move to the dead-letter queue.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class QueueMessage:
    """A message in the queue."""

    body: dict[str, Any]
    message_type: str
    queue_name: str = ""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    receive_count: int = 0
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    visibility_deadline: datetime | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class DeadLetterMessage:
    """A message that has exceeded maximum delivery attempts."""

    original_message: QueueMessage
    original_queue: str
    failure_reason: str
    dead_lettered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class QueueStats:
    """Operational statistics for a queue."""

    queue_name: str
    depth: int
    in_flight: int
    dead_letter_count: int
    total_enqueued: int
    total_acked: int
    total_nacked: int


class Queue(ABC):
    """Abstract queue interface. All broker implementations satisfy this contract."""

    @abstractmethod
    async def enqueue(self, message: QueueMessage) -> None:
        """Add a message to the queue."""
        ...

    @abstractmethod
    async def dequeue(
        self,
        queue_name: str,
        visibility_timeout_seconds: int = 30,
        max_messages: int = 1,
    ) -> list[QueueMessage]:
        """
        Retrieve messages from the queue.

        Messages become invisible to other consumers for visibility_timeout_seconds.
        If not ack'd within that window, they become visible again automatically.
        """
        ...

    @abstractmethod
    async def ack(self, queue_name: str, message_id: str) -> None:
        """Acknowledge successful processing — removes the message permanently."""
        ...

    @abstractmethod
    async def nack(self, queue_name: str, message_id: str, requeue: bool = True) -> None:
        """
        Negatively acknowledge a message.

        If requeue=True and receive_count < max_receive_count, the message is
        re-enqueued for retry. Otherwise it moves to the dead-letter queue.
        """
        ...

    @abstractmethod
    async def get_stats(self, queue_name: str) -> QueueStats:
        """Return current operational statistics for the named queue."""
        ...

    @abstractmethod
    async def get_dead_letters(self, queue_name: str) -> list[DeadLetterMessage]:
        """Return all dead-lettered messages for the named queue."""
        ...
