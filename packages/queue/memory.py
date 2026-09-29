"""
LEDGER-ORBIT: In-Memory Queue Implementation
=============================================
Thread-safe, asyncio-compatible queue for development and testing.
Implements the full Queue interface without external dependencies.

IMPORTANT: NOT suitable for production use:
  - State is lost on restart (no persistence)
  - Does not support multiple processes
  - Does not support distributed consumers
  Exists to allow full system development without a message broker.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Any

from packages.queue.base import DeadLetterMessage, Queue, QueueMessage, QueueStats
from packages.logging.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_RECEIVE_COUNT = 5


class InMemoryQueue(Queue):
    """
    In-memory queue implementation for development and testing.

    Supports:
    - Multiple named queues
    - Visibility timeout (SQS-style crash recovery)
    - Automatic retry on timeout
    - Dead-letter queue after max_receive_count failures
    - Full QueueStats reporting
    """

    def __init__(self, max_receive_count: int = DEFAULT_MAX_RECEIVE_COUNT) -> None:
        self._max_receive_count = max_receive_count
        self._lock = asyncio.Lock()
        # queue_name → deque of (visible_at, QueueMessage)
        self._queues: dict[str, deque[tuple[datetime | None, QueueMessage]]] = defaultdict(deque)
        # queue_name → {message_id → QueueMessage} (in-flight, awaiting ack/nack)
        self._in_flight: dict[str, dict[str, QueueMessage]] = defaultdict(dict)
        # queue_name → list of DeadLetterMessage
        self._dead_letters: dict[str, list[DeadLetterMessage]] = defaultdict(list)
        # Counters
        self._total_enqueued: dict[str, int] = defaultdict(int)
        self._total_acked: dict[str, int] = defaultdict(int)
        self._total_nacked: dict[str, int] = defaultdict(int)

    async def enqueue(self, message: QueueMessage) -> None:
        async with self._lock:
            message.queue_name = message.queue_name or "default"
            self._queues[message.queue_name].append((None, message))
            self._total_enqueued[message.queue_name] += 1
            logger.debug(
                "Message enqueued",
                extra={
                    "queue": message.queue_name,
                    "message_id": message.message_id,
                    "message_type": message.message_type,
                },
            )

    async def dequeue(
        self,
        queue_name: str,
        visibility_timeout_seconds: int = 30,
        max_messages: int = 1,
    ) -> list[QueueMessage]:
        now = datetime.now(timezone.utc)
        results: list[QueueMessage] = []

        async with self._lock:
            queue = self._queues[queue_name]
            remaining: deque[tuple[datetime | None, QueueMessage]] = deque()

            for visible_at, msg in queue:
                if len(results) >= max_messages:
                    remaining.append((visible_at, msg))
                    continue

                if visible_at is not None and now < visible_at:
                    remaining.append((visible_at, msg))
                    continue

                deadline = now + timedelta(seconds=visibility_timeout_seconds)
                msg.receive_count += 1
                msg.visibility_deadline = deadline
                self._in_flight[queue_name][msg.message_id] = msg
                results.append(msg)
                remaining.append((deadline, msg))

            self._queues[queue_name] = remaining

        return results

    async def ack(self, queue_name: str, message_id: str) -> None:
        async with self._lock:
            self._in_flight[queue_name].pop(message_id, None)
            self._queues[queue_name] = deque(
                (vis, msg)
                for vis, msg in self._queues[queue_name]
                if msg.message_id != message_id
            )
            self._total_acked[queue_name] += 1
            logger.debug("Message acked", extra={"queue": queue_name, "message_id": message_id})

    async def nack(self, queue_name: str, message_id: str, requeue: bool = True) -> None:
        async with self._lock:
            msg = self._in_flight[queue_name].pop(message_id, None)
            self._total_nacked[queue_name] += 1

            if msg is None:
                logger.warning(
                    "nack called for unknown message",
                    extra={"queue": queue_name, "message_id": message_id},
                )
                return

            if requeue and msg.receive_count < self._max_receive_count:
                self._queues[queue_name] = deque(
                    (vis, m)
                    for vis, m in self._queues[queue_name]
                    if m.message_id != message_id
                )
                self._queues[queue_name].append((None, msg))
                logger.info(
                    "Message re-queued after nack",
                    extra={"queue": queue_name, "message_id": message_id, "receive_count": msg.receive_count},
                )
            else:
                self._queues[queue_name] = deque(
                    (vis, m)
                    for vis, m in self._queues[queue_name]
                    if m.message_id != message_id
                )
                dlm = DeadLetterMessage(
                    original_message=msg,
                    original_queue=queue_name,
                    failure_reason=f"Exceeded max_receive_count ({self._max_receive_count})",
                )
                self._dead_letters[queue_name].append(dlm)
                logger.warning(
                    "Message dead-lettered",
                    extra={"queue": queue_name, "message_id": message_id, "receive_count": msg.receive_count},
                )

    async def get_stats(self, queue_name: str) -> QueueStats:
        now = datetime.now(timezone.utc)
        async with self._lock:
            visible = sum(
                1
                for vis, _ in self._queues[queue_name]
                if vis is None or now >= vis
            )
            in_flight = len(self._in_flight[queue_name])
            return QueueStats(
                queue_name=queue_name,
                depth=visible,
                in_flight=in_flight,
                dead_letter_count=len(self._dead_letters[queue_name]),
                total_enqueued=self._total_enqueued[queue_name],
                total_acked=self._total_acked[queue_name],
                total_nacked=self._total_nacked[queue_name],
            )

    async def get_dead_letters(self, queue_name: str) -> list[DeadLetterMessage]:
        async with self._lock:
            return list(self._dead_letters[queue_name])
