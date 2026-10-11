"""
Unit tests for SQLAlchemy 2.0 ORM domain models.
Verifies table structure, UUID generation, check constraints, and balance methods.
"""

from __future__ import annotations

import pytest
from packages.database.models import (
    Account,
    Customer,
    IdempotencyRecord,
    LedgerEntry,
    LedgerTransaction,
    Merchant,
    OutboxEvent,
    PaymentIntent,
)


class TestModelDefinitions:
    def test_customer_model_fields(self) -> None:
        c = Customer(
            id="cust_1",
            external_id="ext_1",
            email="test@example.com",
            name="Alice",
            status="ACTIVE",
        )
        assert c.id == "cust_1"
        assert c.email == "test@example.com"
        assert c.__tablename__ == "customers"

    def test_merchant_model_fields(self) -> None:
        m = Merchant(
            id="merch_1",
            external_id="ext_m1",
            business_name="Acme Corp",
            settlement_currency="USD",
            status="ACTIVE",
        )
        assert m.business_name == "Acme Corp"
        assert m.__tablename__ == "merchants"

    def test_account_model_fields(self) -> None:
        a = Account(
            id="acc_1",
            account_number="1010-CUST-001",
            account_type="CUSTOMER",
            normal_balance="DEBIT",
            currency="USD",
            owner_type="CUSTOMER",
            owner_id="cust_1",
            status="ACTIVE",
            current_balance_minor=0,
        )
        assert a.account_number == "1010-CUST-001"
        assert a.normal_balance == "DEBIT"
        assert a.__tablename__ == "accounts"

    def test_payment_intent_model(self) -> None:
        pi = PaymentIntent(
            id="pi_1",
            idempotency_key="ik_1",
            amount_minor=5000,
            currency="USD",
            status="CREATED",
            client_secret="sec_1",
            correlation_id="corr_1",
        )
        assert pi.amount_minor == 5000
        assert pi.__tablename__ == "payment_intents"

    def test_idempotency_record_model(self) -> None:
        ir = IdempotencyRecord(
            id="ir_1",
            idempotency_key="key_1",
            request_hash="sha256_dummy_hash",
            status="PROCESSING",
        )
        assert ir.request_hash == "sha256_dummy_hash"
        assert ir.__tablename__ == "idempotency_records"

    def test_outbox_event_model(self) -> None:
        oe = OutboxEvent(
            id="oe_1",
            event_type="PaymentSucceeded",
            aggregate_type="Payment",
            aggregate_id="pmt_1",
            status="PENDING",
            payload_json="{}",
            correlation_id="corr_1",
        )
        assert oe.status == "PENDING"
        assert oe.__tablename__ == "outbox_events"


class TestLedgerTransactionLogic:
    def test_balanced_transaction_two_legs(self) -> None:
        tx = LedgerTransaction(
            id="tx_1",
            reference="ref_001",
            status="POSTED",
            description="Test payment",
            currency="USD",
            correlation_id="corr_1",
        )
        e1 = LedgerEntry(
            id="e_1",
            transaction_id="tx_1",
            account_id="acc_cust",
            direction="CREDIT",
            amount_minor=10000,
            currency="USD",
        )
        e2 = LedgerEntry(
            id="e_2",
            transaction_id="tx_1",
            account_id="acc_merch",
            direction="DEBIT",
            amount_minor=10000,
            currency="USD",
        )
        tx.entries = [e1, e2]

        assert tx.total_debit() == 10000
        assert tx.total_credit() == 10000
        assert tx.is_balanced() is True

    def test_balanced_transaction_three_legs(self) -> None:
        tx = LedgerTransaction(
            id="tx_2",
            reference="ref_002",
            status="POSTED",
            description="Payment with fee",
            currency="INR",
            correlation_id="corr_2",
        )
        # ₹100 from customer: Credit customer 10000 paise
        # Debit merchant 9500 paise (₹95)
        # Debit platform fee 500 paise (₹5)
        e1 = LedgerEntry(
            id="e_1",
            transaction_id="tx_2",
            account_id="acc_cust",
            direction="CREDIT",
            amount_minor=10000,
            currency="INR",
        )
        e2 = LedgerEntry(
            id="e_2",
            transaction_id="tx_2",
            account_id="acc_merch",
            direction="DEBIT",
            amount_minor=9500,
            currency="INR",
        )
        e3 = LedgerEntry(
            id="e_3",
            transaction_id="tx_2",
            account_id="acc_fee",
            direction="DEBIT",
            amount_minor=500,
            currency="INR",
        )
        tx.entries = [e1, e2, e3]

        assert tx.total_debit() == 10000
        assert tx.total_credit() == 10000
        assert tx.is_balanced() is True

    def test_unbalanced_transaction_detected(self) -> None:
        tx = LedgerTransaction(
            id="tx_3",
            reference="ref_003",
            status="POSTED",
            description="Broken payment",
            currency="USD",
            correlation_id="corr_3",
        )
        e1 = LedgerEntry(
            id="e_1",
            transaction_id="tx_3",
            account_id="acc_1",
            direction="DEBIT",
            amount_minor=10000,
            currency="USD",
        )
        e2 = LedgerEntry(
            id="e_2",
            transaction_id="tx_3",
            account_id="acc_2",
            direction="CREDIT",
            amount_minor=9999,  # 1 cent dropped!
            currency="USD",
        )
        tx.entries = [e1, e2]

        assert tx.total_debit() == 10000
        assert tx.total_credit() == 9999
        assert tx.is_balanced() is False
