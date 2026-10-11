"""
LEDGER-ORBIT: Ledger ORM Models
===============================
Double-entry financial journal models: LedgerTransaction and LedgerEntry.

DESIGN DECISIONS:
  - Ledger immutability: posted ledger entries are append-only.
  - Every entry belongs to a transaction and an account.
  - Direction is strictly DEBIT or CREDIT.
  - amount_minor is always a positive integer (> 0).
  - Mathematical invariant: sum(Debits) == sum(Credits) for every transaction.
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
    from packages.database.models.entities import Account


class LedgerTransaction(Base, UUIDMixin, TimestampMixin):
    """
    Represents a balanced multi-legged financial transaction.
    Comprises two or more LedgerEntry legs.
    """

    __tablename__ = "ledger_transactions"

    reference: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique business reference (e.g. tx_01HX9A7B)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="POSTED",
        nullable=False,
        comment="Transaction status: PENDING, POSTED, REVERSED, FAILED",
    )
    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Human-readable transaction description",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="ISO-4217 currency code (e.g. USD, INR, EUR)",
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="Distributed tracing correlation ID",
    )
    causation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="ID of the event or request that caused this transaction",
    )
    related_transaction_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="ID of original transaction if this is a reversal",
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Arbitrary contextual JSON metadata",
    )

    # Relationship to transaction entry legs
    entries: Mapped[List[LedgerEntry]] = relationship(
        "LedgerEntry",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="LedgerEntry.sequence",
    )

    def total_debit(self) -> int:
        """Sum of all DEBIT entry amounts in minor units."""
        return sum(e.amount_minor for e in self.entries if e.direction == "DEBIT")

    def total_credit(self) -> int:
        """Sum of all CREDIT entry amounts in minor units."""
        return sum(e.amount_minor for e in self.entries if e.direction == "CREDIT")

    def is_balanced(self) -> bool:
        """
        Fundamental invariant check: sum(Debits) == sum(Credits).
        Returns True if balanced and at least two entries exist.
        """
        if len(self.entries) < 2:
            return False
        return self.total_debit() == self.total_credit()


class LedgerEntry(Base, UUIDMixin, TimestampMixin):
    """
    An immutable directional leg of a ledger transaction.
    Must always have amount_minor > 0 and direction in ('DEBIT', 'CREDIT').
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="chk_ledger_entry_amount_positive"),
        CheckConstraint(
            "direction IN ('DEBIT', 'CREDIT')",
            name="chk_ledger_entry_direction_valid",
        ),
    )

    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="DEBIT or CREDIT",
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Always positive integer minor unit",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Relationships
    transaction: Mapped[LedgerTransaction] = relationship(
        "LedgerTransaction",
        back_populates="entries",
    )
    account: Mapped[Account] = relationship(
        "Account",
        back_populates="ledger_entries",
    )
