"""
Unit tests for the Money value object.

These tests verify the core financial arithmetic that ALL other components
depend on. A bug here would corrupt every financial calculation in the system.

Test categories:
  1. Construction — valid and invalid inputs
  2. Arithmetic — add, subtract, negate, abs
  3. Comparison — equality, ordering
  4. Multiplication — with banker's rounding
  5. Allocation — penny-perfect distribution
  6. Currency safety — cross-currency protection
  7. State machine — payment transitions
  8. Property-based tests (Hypothesis)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packages.shared_types.money import (
    Currency,
    Money,
    PaymentStatus,
    is_valid_payment_transition,
)


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------


class TestMoneyConstruction:
    def test_valid_construction(self) -> None:
        m = Money(amount_minor=10050, currency=Currency.USD)
        assert m.amount_minor == 10050
        assert m.currency == Currency.USD

    def test_zero_amount_is_valid(self) -> None:
        m = Money.zero(Currency.INR)
        assert m.amount_minor == 0

    def test_negative_amount_is_valid(self) -> None:
        """Negative amounts represent credit entries and balance adjustments."""
        m = Money(amount_minor=-5000, currency=Currency.INR)
        assert m.is_negative()

    def test_float_input_raises_type_error(self) -> None:
        """Float must never be accepted — it silently loses precision."""
        with pytest.raises(TypeError, match="must be an int"):
            Money(amount_minor=100.50, currency=Currency.USD)  # type: ignore[arg-type]

    def test_from_major_decimal(self) -> None:
        m = Money.from_major(Decimal("100.50"), Currency.USD)
        assert m.amount_minor == 10050

    def test_from_major_string(self) -> None:
        m = Money.from_major("50.25", Currency.INR)
        assert m.amount_minor == 5025

    def test_from_major_int(self) -> None:
        m = Money.from_major(100, Currency.EUR)
        assert m.amount_minor == 10000

    def test_str_representation(self) -> None:
        m = Money.from_major("100.50", Currency.USD)
        assert str(m) == "$100.50"

    def test_immutability(self) -> None:
        """Money instances must be immutable (frozen dataclass)."""
        m = Money(amount_minor=1000, currency=Currency.USD)
        with pytest.raises((AttributeError, TypeError)):
            m.amount_minor = 2000  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Arithmetic
# ---------------------------------------------------------------------------


class TestMoneyArithmetic:
    def test_add(self) -> None:
        a = Money(10000, Currency.USD)
        b = Money(500, Currency.USD)
        assert (a + b).amount_minor == 10500

    def test_subtract(self) -> None:
        a = Money(10000, Currency.USD)
        b = Money(500, Currency.USD)
        assert (a - b).amount_minor == 9500

    def test_negate(self) -> None:
        m = Money(10000, Currency.USD)
        assert (-m).amount_minor == -10000

    def test_abs_positive(self) -> None:
        m = Money(10000, Currency.USD)
        assert abs(m).amount_minor == 10000

    def test_abs_negative(self) -> None:
        m = Money(-10000, Currency.USD)
        assert abs(m).amount_minor == 10000

    def test_arithmetic_returns_new_instance(self) -> None:
        a = Money(10000, Currency.USD)
        b = Money(500, Currency.USD)
        c = a + b
        assert c is not a
        assert a.amount_minor == 10000  # original unchanged


# ---------------------------------------------------------------------------
# 3. Comparison
# ---------------------------------------------------------------------------


class TestMoneyComparison:
    def test_equality_same_amount_same_currency(self) -> None:
        assert Money(100, Currency.USD) == Money(100, Currency.USD)

    def test_inequality_different_amount(self) -> None:
        assert Money(100, Currency.USD) != Money(200, Currency.USD)

    def test_inequality_different_currency(self) -> None:
        assert Money(100, Currency.USD) != Money(100, Currency.INR)

    def test_ordering(self) -> None:
        small = Money(100, Currency.USD)
        large = Money(200, Currency.USD)
        assert small < large
        assert large > small
        assert small <= Money(100, Currency.USD)
        assert small >= Money(100, Currency.USD)


# ---------------------------------------------------------------------------
# 4. Currency Safety
# ---------------------------------------------------------------------------


class TestCurrencySafety:
    def test_add_different_currencies_raises(self) -> None:
        a = Money(100, Currency.USD)
        b = Money(100, Currency.INR)
        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = a + b

    def test_subtract_different_currencies_raises(self) -> None:
        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = Money(100, Currency.USD) - Money(100, Currency.EUR)

    def test_compare_different_currencies_raises(self) -> None:
        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = Money(100, Currency.USD) < Money(100, Currency.INR)


# ---------------------------------------------------------------------------
# 5. Multiplication with Banker's Rounding
# ---------------------------------------------------------------------------


class TestMoneyMultiplication:
    def test_multiply_whole_result(self) -> None:
        m = Money(10000, Currency.USD)  # $100.00
        result = m.multiply_by_factor(Decimal("0.05"))  # 5%
        assert result.amount_minor == 500  # $5.00

    def test_multiply_half_even_rounding(self) -> None:
        """
        ROUND_HALF_EVEN (banker's rounding):
          2.5 → 2 (rounds to even)
          3.5 → 4 (rounds to even)
        """
        m = Money(5, Currency.USD)  # 5 cents
        result = m.multiply_by_factor(Decimal("0.5"))  # 2.5 → 2
        assert result.amount_minor == 2

    def test_multiply_preserves_currency(self) -> None:
        m = Money(10000, Currency.INR)
        result = m.multiply_by_factor("0.025")
        assert result.currency == Currency.INR


# ---------------------------------------------------------------------------
# 6. Allocation (Penny-Perfect Distribution)
# ---------------------------------------------------------------------------


class TestMoneyAllocation:
    def test_equal_split_no_penny_loss(self) -> None:
        """Splitting 10 cents 3 ways must account for all 10 cents."""
        m = Money(10, Currency.USD)
        parts = m.allocate([1, 1, 1])
        assert len(parts) == 3
        assert sum(p.amount_minor for p in parts) == 10

    def test_weighted_split(self) -> None:
        m = Money(10000, Currency.USD)  # $100
        parts = m.allocate([70, 20, 10])  # 70/20/10%
        assert sum(p.amount_minor for p in parts) == 10000
        assert parts[0].amount_minor == 7000
        assert parts[1].amount_minor == 2000
        assert parts[2].amount_minor == 1000

    def test_allocation_invariant_sum_equals_total(self) -> None:
        """For any reasonable split, sum of parts must equal the whole."""
        m = Money(9999, Currency.INR)  # odd amount
        parts = m.allocate([1, 1, 1])
        assert sum(p.amount_minor for p in parts) == 9999

    def test_empty_ratios_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            Money(100, Currency.USD).allocate([])

    def test_zero_ratio_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Money(100, Currency.USD).allocate([1, 0, 1])

    def test_single_ratio_returns_full_amount(self) -> None:
        m = Money(5000, Currency.USD)
        parts = m.allocate([1])
        assert len(parts) == 1
        assert parts[0] == m


# ---------------------------------------------------------------------------
# 7. Payment State Machine
# ---------------------------------------------------------------------------


class TestPaymentStateMachine:
    def test_created_to_processing_valid(self) -> None:
        assert is_valid_payment_transition(PaymentStatus.CREATED, PaymentStatus.PROCESSING)

    def test_created_to_succeeded_invalid(self) -> None:
        assert not is_valid_payment_transition(PaymentStatus.CREATED, PaymentStatus.SUCCEEDED)

    def test_processing_to_succeeded_valid(self) -> None:
        assert is_valid_payment_transition(PaymentStatus.PROCESSING, PaymentStatus.SUCCEEDED)

    def test_processing_to_failed_valid(self) -> None:
        assert is_valid_payment_transition(PaymentStatus.PROCESSING, PaymentStatus.FAILED)

    def test_succeeded_to_refunded_valid(self) -> None:
        assert is_valid_payment_transition(PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED)

    def test_cancelled_has_no_valid_transitions(self) -> None:
        for status in PaymentStatus:
            assert not is_valid_payment_transition(PaymentStatus.CANCELLED, status)

    def test_refunded_has_no_valid_transitions(self) -> None:
        for status in PaymentStatus:
            assert not is_valid_payment_transition(PaymentStatus.REFUNDED, status)


# ---------------------------------------------------------------------------
# 8. Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------


class TestMoneyProperties:
    @given(st.integers(min_value=0, max_value=10_000_000))
    def test_add_commutativity(self, x: int) -> None:
        """a + b == b + a for all valid amounts."""
        a = Money(x, Currency.USD)
        b = Money(x // 2, Currency.USD)
        assert a + b == b + a

    @given(st.integers(min_value=1, max_value=10_000_000))
    def test_add_negation_identity(self, x: int) -> None:
        """m + (-m) == 0."""
        m = Money(x, Currency.USD)
        assert (m + (-m)).is_zero()

    @given(
        total=st.integers(min_value=0, max_value=1_000_000),
        ratios=st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=10),
    )
    def test_allocation_sum_invariant(self, total: int, ratios: list[int]) -> None:
        """sum(allocate(ratios)) == total for all inputs — penny-perfect guarantee."""
        m = Money(total, Currency.USD)
        parts = m.allocate(ratios)
        assert sum(p.amount_minor for p in parts) == total
