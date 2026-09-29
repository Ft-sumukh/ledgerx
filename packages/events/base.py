"""
LEDGER-ORBIT: Domain Event System
====================================
Defines typed domain events and the transactional outbox pattern.

DESIGN DECISIONS:
  - schema_version supports backward-compatible event schema evolution.
  - correlation_id connects related events across service boundaries.
  - OutboxEvent is persisted in the same DB transaction as financial state
    (transactional outbox pattern) to prevent dual-write failures.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Typed domain event identifiers for LEDGER-ORBIT."""

    # Payment lifecycle
    PAYMENT_CREATED = "PaymentCreated"
    PAYMENT_PROCESSING = "PaymentProcessing"
    PAYMENT_SUCCEEDED = "PaymentSucceeded"
    PAYMENT_FAILED = "PaymentFailed"
    PAYMENT_CANCELLED = "PaymentCancelled"

    # Refunds
    REFUND_CREATED = "RefundCreated"
    REFUND_PROCESSED = "RefundProcessed"

    # Ledger
    LEDGER_TRANSACTION_POSTED = "LedgerTransactionPosted"

    # Settlement
    SETTLEMENT_CREATED = "SettlementCreated"
    SETTLEMENT_COMPLETED = "SettlementCompleted"

    # Webhooks
    WEBHOOK_RECEIVED = "WebhookReceived"
    WEBHOOK_PROCESSED = "WebhookProcessed"
    WEBHOOK_FAILED = "WebhookFailed"

    # Jobs
    JOB_CREATED = "JobCreated"
    JOB_COMPLETED = "JobCompleted"
    JOB_FAILED = "JobFailed"
    JOB_DEAD_LETTERED = "JobDeadLettered"

    # Reconciliation
    RECONCILIATION_STARTED = "ReconciliationStarted"
    RECONCILIATION_COMPLETED = "ReconciliationCompleted"

    # Auth
    USER_AUTHENTICATED = "UserAuthenticated"
    USER_AUTHENTICATION_FAILED = "UserAuthenticationFailed"


class DomainEvent(BaseModel):
    """
    Base domain event — unit of communication between LEDGER-ORBIT components.

    event_id guarantees exactly-once processing when consumers implement deduplication.
    correlation_id traces the event back to the originating API request.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    aggregate_id: str
    aggregate_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: str | None = None

    model_config = {"frozen": True}


class OutboxEventStatus(StrEnum):
    """Status of an outbox event in the transactional outbox."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class OutboxEvent(BaseModel):
    """
    Transactional outbox record.

    Persisted in the same database transaction as the financial state change.
    The outbox publisher reads PENDING records and publishes them to the broker,
    then marks them PUBLISHED.

    This guarantees that financial state changes and events are always in sync,
    even when the message broker is temporarily unavailable.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event: DomainEvent
    queue_name: str
    status: OutboxEventStatus = OutboxEventStatus.PENDING
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None
    last_error: str | None = None
