"""
LEDGER-ORBIT: Shared Types Package
===================================
Financial domain primitives: Money, Currency, account types, payment states.

DESIGN PRINCIPLE — ZERO FLOATING-POINT:
  All monetary amounts are represented as exact integers in minor currency units.
  Example: USD $100.50 → amount_minor=10050, currency=Currency.USD
  Example: INR ₹50.25  → amount_minor=5025,  currency=Currency.INR
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Sequence


class Currency(StrEnum):
    """ISO-4217 currency codes supported by LEDGER-ORBIT."""

    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"

    @property
    def minor_unit_factor(self) -> int:
        return 100

    @property
    def symbol(self) -> str:
        symbols = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
        return symbols[self.value]


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """
    Immutable money value object using integer minor-unit representation.

    Args:
        amount_minor: Amount in the currency's smallest unit (always int).
        currency:     ISO-4217 currency code.

    Raises:
        TypeError:  If amount_minor is not an int.
        ValueError: If currency types differ during arithmetic.
    """

    amount_minor: int
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError(
                f"Money.amount_minor must be an int (got {type(self.amount_minor).__name__}). "
                "Never use float for financial amounts."
            )

    @classmethod
    def from_major(cls, amount: "Decimal | str | int", currency: Currency) -> "Money":
        """Create Money from a major-unit decimal amount using banker's rounding."""
        d = Decimal(str(amount))
        factor = Decimal(currency.minor_unit_factor)
        minor = int((d * factor).to_integral_value(rounding=ROUND_HALF_EVEN))
        return cls(amount_minor=minor, currency=currency)

    @classmethod
    def zero(cls, currency: Currency) -> "Money":
        return cls(amount_minor=0, currency=currency)

    def as_major(self) -> Decimal:
        return Decimal(self.amount_minor) / Decimal(self.currency.minor_unit_factor)

    def __str__(self) -> str:
        return f"{self.currency.symbol}{self.as_major():.2f}"

    def __repr__(self) -> str:
        return f"Money(amount_minor={self.amount_minor}, currency={self.currency!r})"

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: cannot combine {self.currency} and {other.currency}."
            )

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount_minor, self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount_minor), self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount_minor == other.amount_minor and self.currency == other.currency

    def __lt__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount_minor >= other.amount_minor

    def multiply_by_factor(self, factor: "Decimal | str") -> "Money":
        """Multiply by a rational factor using banker's rounding. Never accepts float."""
        d = Decimal(str(factor))
        result = Decimal(self.amount_minor) * d
        return Money(
            int(result.to_integral_value(rounding=ROUND_HALF_EVEN)),
            self.currency,
        )

    def allocate(self, ratios: Sequence[int]) -> list["Money"]:
        """
        Distribute self proportionally without losing a penny (Largest Remainder Method).

        sum(allocate(ratios)) == self is guaranteed for all valid inputs.
        """
        if not ratios:
            raise ValueError("ratios must be non-empty")
        if any(r <= 0 for r in ratios):
            raise ValueError("All ratios must be positive integers")

        total_ratio = sum(ratios)
        total_minor = self.amount_minor
        raw_shares = [(r / total_ratio) * total_minor for r in ratios]
        floored = [math.floor(s) for s in raw_shares]
        remainders = [raw - fl for raw, fl in zip(raw_shares, floored)]
        leftover = total_minor - sum(floored)
        indices_by_remainder = sorted(
            range(len(remainders)), key=lambda i: (-remainders[i], i)
        )
        for i in range(leftover):
            floored[indices_by_remainder[i]] += 1
        return [Money(amount_minor=f, currency=self.currency) for f in floored]

    def is_zero(self) -> bool:
        return self.amount_minor == 0

    def is_positive(self) -> bool:
        return self.amount_minor > 0

    def is_negative(self) -> bool:
        return self.amount_minor < 0


class AccountType(StrEnum):
    CUSTOMER = "CUSTOMER"
    MERCHANT = "MERCHANT"
    PLATFORM = "PLATFORM"
    FEES = "FEES"
    SETTLEMENT = "SETTLEMENT"
    RESERVE = "RESERVE"


class EntryDirection(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class AccountCategory(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


def normal_balance_for_category(category: AccountCategory) -> NormalBalance:
    """Returns the normal accounting balance direction for a fundamental category."""
    if category in (AccountCategory.ASSET, AccountCategory.EXPENSE):
        return NormalBalance.DEBIT
    return NormalBalance.CREDIT


class NormalBalance(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


PAYMENT_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.CREATED: frozenset([PaymentStatus.PROCESSING, PaymentStatus.CANCELLED]),
    PaymentStatus.PROCESSING: frozenset([PaymentStatus.SUCCEEDED, PaymentStatus.FAILED]),
    PaymentStatus.SUCCEEDED: frozenset([PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]),
    PaymentStatus.FAILED: frozenset([PaymentStatus.PROCESSING]),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
    PaymentStatus.PARTIALLY_REFUNDED: frozenset([PaymentStatus.REFUNDED]),
}


def is_valid_payment_transition(current: PaymentStatus, next_status: PaymentStatus) -> bool:
    return next_status in PAYMENT_TRANSITIONS.get(current, frozenset())


class JobStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    DEAD_LETTERED = "DEAD_LETTERED"


class WorkerStatus(StrEnum):
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"


class OwnerType(StrEnum):
    CUSTOMER = "CUSTOMER"
    MERCHANT = "MERCHANT"
    PLATFORM = "PLATFORM"
