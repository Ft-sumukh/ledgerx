"""
LEDGER-ORBIT: Relational Entity Models
=======================================
Defines Customer, Merchant, Account, PaymentIntent, IdempotencyRecord, and OutboxEvent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from packages.database.models.ledger import LedgerEntry


class Customer(Base, UUIDMixin, TimestampMixin):
    """Represents an individual customer identity."""

    __tablename__ = "customers"

    external_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique identifier in client external system",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="ACTIVE",
        nullable=False,
        comment="ACTIVE, SUSPENDED, DELETED",
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    accounts: Mapped[List[Account]] = relationship(
        "Account",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    payment_intents: Mapped[List[PaymentIntent]] = relationship(
        "PaymentIntent",
        back_populates="customer",
    )


class Merchant(Base, UUIDMixin, TimestampMixin):
    """Represents a business merchant selling goods or services."""

    __tablename__ = "merchants"

    external_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    business_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    settlement_currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="ACTIVE",
        nullable=False,
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    accounts: Mapped[List[Account]] = relationship(
        "Account",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )
    payment_intents: Mapped[List[PaymentIntent]] = relationship(
        "PaymentIntent",
        back_populates="merchant",
    )


class Account(Base, UUIDMixin, TimestampMixin):
    """
    Financial Account representing an asset, liability, equity, revenue, or expense ledger node.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('CUSTOMER', 'MERCHANT', 'PLATFORM', 'FEES', 'SETTLEMENT', 'RESERVE')",
            name="chk_account_type_valid",
        ),
        CheckConstraint(
            "normal_balance IN ('DEBIT', 'CREDIT')",
            name="chk_account_normal_balance_valid",
        ),
    )

    account_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Hierarchical chart-of-accounts number, e.g. 1010-CUST-001",
    )
    account_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="CUSTOMER, MERCHANT, PLATFORM, FEES, SETTLEMENT, RESERVE",
    )
    normal_balance: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="DEBIT or CREDIT",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="ISO-4217 Currency (USD, EUR, INR, GBP)",
    )
    owner_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="CUSTOMER, MERCHANT, PLATFORM",
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(36),
        index=True,
        nullable=True,
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    merchant_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("merchants.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE",
        nullable=False,
        comment="ACTIVE, FROZEN, CLOSED",
    )
    current_balance_minor: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
        comment="Materialized signed balance in minor units",
    )

    # Relationships
    customer: Mapped[Customer | None] = relationship(
        "Customer",
        back_populates="accounts",
    )
    merchant: Mapped[Merchant | None] = relationship(
        "Merchant",
        back_populates="accounts",
    )
    ledger_entries: Mapped[List[LedgerEntry]] = relationship(
        "LedgerEntry",
        back_populates="account",
    )


class PaymentIntent(Base, UUIDMixin, TimestampMixin):
    """
    Orchestrates the lifecycle of an inbound payment transaction.
    """

    __tablename__ = "payment_intents"

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("customers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    merchant_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("merchants.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="CREATED",
        nullable=False,
        comment="CREATED, PROCESSING, SUCCEEDED, FAILED, CANCELLED, REFUNDED, PARTIALLY_REFUNDED",
    )
    client_secret: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    customer: Mapped[Customer | None] = relationship(
        "Customer",
        back_populates="payment_intents",
    )
    merchant: Mapped[Merchant | None] = relationship(
        "Merchant",
        back_populates="payment_intents",
    )


class IdempotencyRecord(Base, UUIDMixin, TimestampMixin):
    """
    Prevents duplicate mutations by storing request payload hashes and responses.
    """

    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of incoming JSON request payload",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="PROCESSING",
        nullable=False,
        comment="PROCESSING, COMPLETED, FAILED",
    )
    response_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    response_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OutboxEvent(Base, UUIDMixin, TimestampMixin):
    """
    Transactional Outbox record storing published domain events atomically with state mutations.
    """

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    aggregate_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        index=True,
        nullable=False,
        comment="PENDING, PUBLISHED, FAILED",
    )
    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
