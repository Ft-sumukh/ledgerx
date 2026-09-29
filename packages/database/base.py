"""
LEDGER-ORBIT: Database Base Models
====================================
SQLAlchemy 2.0 declarative base and common mixins.

DESIGN DECISIONS:
  - UUID primary keys prevent enumeration attacks and distribute well across partitions.
  - created_at / updated_at always stored in UTC to avoid timezone bugs.
  - UUIDMixin and TimestampMixin use __abstract__ = True so SQLAlchemy does
    not create tables for them directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all LEDGER-ORBIT domain models."""
    pass


class UUIDMixin:
    """Provides a UUID primary key column."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class TimestampMixin:
    """Provides created_at and updated_at UTC timestamp columns."""

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
