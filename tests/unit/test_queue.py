"""
Unit tests for InMemoryQueue.

Verify the full queue contract:
  - enqueue / dequeue
  - ack (successful processing)
  - nack + requeue (retry)
  - nack + dead-letter (max attempts exceeded)
  - visibility timeout behavior
  - queue stats accuracy
"""

from __future__ import annotations

import pytest

from packages.queue.base import QueueMessage
from packages.queue.memory import InMemoryQueue


@pytest.fixture
def queue() -> InMemoryQueue:
    return InMemoryQueue(max_receive_count=3)


def make_message(msg_type: str = "TestEvent", queue_name: str = "test") -> QueueMessage:
    return QueueMessage(
        body={"test": True},
        message_type=msg_type,
        queue_name=queue_name,
    )


@pytest.mark.asyncio
class TestEnqueueDequeue:
    async def test_enqueue_and_dequeue_single_message(self, queue: InMemoryQueue) -> None:
        msg = make_message()
        await queue.enqueue(msg)
        received = await queue.dequeue("test", max_messages=1)
        assert len(received) == 1
        assert received[0].message_id == msg.message_id

    async def test_dequeue_empty_queue_returns_empty_list(self, queue: InMemoryQueue) -> None:
        received = await queue.dequeue("empty_queue")
        assert received == []

    async def test_dequeue_respects_max_messages(self, queue: InMemoryQueue) -> None:
        for _ in range(5):
            await queue.enqueue(make_message())
        received = await queue.dequeue("test", max_messages=3)
        assert len(received) == 3

    async def test_message_receive_count_increments(self, queue: InMemoryQueue) -> None:
        await queue.enqueue(make_message())
        received = await queue.dequeue("test")
        assert received[0].receive_count == 1

    async def test_multiple_queue_names_are_independent(self, queue: InMemoryQueue) -> None:
        await queue.enqueue(QueueMessage(body={}, message_type="A", queue_name="q1"))
        await queue.enqueue(QueueMessage(body={}, message_type="B", queue_name="q2"))
        r1 = await queue.dequeue("q1")
        r2 = await queue.dequeue("q2")
        assert r1[0].message_type == "A"
        assert r2[0].message_type == "B"


@pytest.mark.asyncio
class TestAck:
    async def test_ack_removes_message(self, queue: InMemoryQueue) -> None:
        msg = make_message()
        await queue.enqueue(msg)
        received = await queue.dequeue("test")
        await queue.ack("test", received[0].message_id)
        stats = await queue.get_stats("test")
        assert stats.total_acked == 1

    async def test_acked_message_not_redelivered(self, queue: InMemoryQueue) -> None:
        msg = make_message()
        await queue.enqueue(msg)
        received = await queue.dequeue("test")
        await queue.ack("test", received[0].message_id)
        received2 = await queue.dequeue("test", visibility_timeout_seconds=0)
        assert len(received2) == 0


@pytest.mark.asyncio
class TestNack:
    async def test_nack_with_requeue_makes_message_available(self, queue: InMemoryQueue) -> None:
        await queue.enqueue(make_message())
        received = await queue.dequeue("test")
        await queue.nack("test", received[0].message_id, requeue=True)
        received2 = await queue.dequeue("test")
        assert len(received2) == 1

    async def test_nack_exceeding_max_receive_count_dead_letters(self, queue: InMemoryQueue) -> None:
        """After max_receive_count nacks, message moves to dead-letter queue."""
        await queue.enqueue(make_message())

        for _ in range(3):
            received = await queue.dequeue("test")
            assert len(received) == 1
            await queue.nack("test", received[0].message_id, requeue=True)

        dead_letters = await queue.get_dead_letters("test")
        assert len(dead_letters) == 1
        assert dead_letters[0].original_queue == "test"

    async def test_nack_without_requeue_goes_to_dlq(self, queue: InMemoryQueue) -> None:
        await queue.enqueue(make_message())
        received = await queue.dequeue("test")
        await queue.nack("test", received[0].message_id, requeue=False)
        dead_letters = await queue.get_dead_letters("test")
        assert len(dead_letters) == 1


@pytest.mark.asyncio
class TestStats:
    async def test_stats_reflect_enqueue_and_ack(self, queue: InMemoryQueue) -> None:
        await queue.enqueue(make_message())
        await queue.enqueue(make_message())

        received = await queue.dequeue("test", max_messages=2)
        for msg in received:
            await queue.ack("test", msg.message_id)

        stats = await queue.get_stats("test")
        assert stats.total_enqueued == 2
        assert stats.total_acked == 2
        assert stats.in_flight == 0

    async def test_dead_letter_count_tracked(self, queue: InMemoryQueue) -> None:
        await queue.enqueue(make_message())
        received = await queue.dequeue("test")
        await queue.nack("test", received[0].message_id, requeue=False)
        stats = await queue.get_stats("test")
        assert stats.dead_letter_count == 1
