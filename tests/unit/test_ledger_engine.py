"""
Unit and integration tests for LedgerRepository and double-entry invariants.
Executes against an isolated in-memory SQLite database.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.repository import (
    AccountCurrencyMismatchError,
    AccountRepository,
    CustomerRepository,
    EntityNotFoundError,
    LedgerRepository,
    LedgerUnbalancedError,
    MerchantRepository,
)
from packages.database.schemas import (
    AccountCreate,
    CustomerCreate,
    LedgerEntryInput,
    LedgerTransactionCreate,
    MerchantCreate,
)
from packages.shared_types.money import (
    AccountType,
    Currency,
    EntryDirection,
)


@pytest.fixture
async def async_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


class TestLedgerEnginePipeline:
    @pytest.mark.asyncio
    async def test_post_balanced_two_legged_transaction(self, async_session: AsyncSession) -> None:
        cust_repo = CustomerRepository(async_session)
        acc_repo = AccountRepository(async_session)
        ledger_repo = LedgerRepository(async_session)

        # 1. Create customer and accounts
        cust = await cust_repo.create(
            CustomerCreate(external_id="ext_100", email="alice@test.com", name="Alice")
        )
        acc_cust = await acc_repo.create(
            AccountCreate(
                account_number="1010-ALICE",
                account_type=AccountType.CUSTOMER,
                currency=Currency.USD,
                owner_type="CUSTOMER",
                customer_id=cust.id,
            )
        )
        acc_merch = await acc_repo.create(
            AccountCreate(
                account_number="2010-STORE",
                account_type=AccountType.MERCHANT,
                currency=Currency.USD,
                owner_type="MERCHANT",
            )
        )

        # 2. Post transaction: $50.00 (5000 cents)
        tx_in = LedgerTransactionCreate(
            reference="tx_alice_store_01",
            description="Alice buys shoes",
            currency=Currency.USD,
            entries=[
                LedgerEntryInput(
                    account_id=acc_cust.id,
                    direction=EntryDirection.CREDIT,
                    amount_minor=5000,
                    currency=Currency.USD,
                ),
                LedgerEntryInput(
                    account_id=acc_merch.id,
                    direction=EntryDirection.DEBIT,
                    amount_minor=5000,
                    currency=Currency.USD,
                ),
            ],
        )

        tx = await ledger_repo.post_transaction(tx_in, correlation_id="corr_test_1")

        assert tx.id is not None
        assert tx.reference == "tx_alice_store_01"
        assert tx.status == "POSTED"
        assert len(tx.entries) == 2
        assert tx.is_balanced() is True

        # Check account balances
        bal_cust = await ledger_repo.derive_account_balance(acc_cust.id)
        bal_merch = await ledger_repo.derive_account_balance(acc_merch.id)
        # Customer normal DEBIT: credit decreases (-5000)
        assert bal_cust == -5000
        # Merchant normal CREDIT: debit decreases (-5000) or credit increases
        assert bal_merch == -5000

    @pytest.mark.asyncio
    async def test_post_balanced_three_legged_transaction(self, async_session: AsyncSession) -> None:
        acc_repo = AccountRepository(async_session)
        ledger_repo = LedgerRepository(async_session)

        acc_cust = await acc_repo.create(
            AccountCreate(
                account_number="1010-BOB",
                account_type=AccountType.CUSTOMER,
                currency=Currency.INR,
                owner_type="CUSTOMER",
            )
        )
        acc_merch = await acc_repo.create(
            AccountCreate(
                account_number="2010-SHOP",
                account_type=AccountType.MERCHANT,
                currency=Currency.INR,
                owner_type="MERCHANT",
            )
        )
        acc_fee = await acc_repo.create(
            AccountCreate(
                account_number="3010-PLATFORM-FEE",
                account_type=AccountType.FEES,
                currency=Currency.INR,
                owner_type="PLATFORM",
            )
        )

        # ₹100 payment: 10000 paise
        # Merchant gets ₹97 (9700), Platform fee ₹3 (300)
        tx_in = LedgerTransactionCreate(
            reference="tx_bob_fee_02",
            description="Bob payment with platform fee",
            currency=Currency.INR,
            entries=[
                LedgerEntryInput(
                    account_id=acc_cust.id,
                    direction=EntryDirection.CREDIT,
                    amount_minor=10000,
                    currency=Currency.INR,
                ),
                LedgerEntryInput(
                    account_id=acc_merch.id,
                    direction=EntryDirection.DEBIT,
                    amount_minor=9700,
                    currency=Currency.INR,
                ),
                LedgerEntryInput(
                    account_id=acc_fee.id,
                    direction=EntryDirection.DEBIT,
                    amount_minor=300,
                    currency=Currency.INR,
                ),
            ],
        )

        tx = await ledger_repo.post_transaction(tx_in, correlation_id="corr_test_2")
        assert tx.is_balanced() is True
        assert len(tx.entries) == 3

    @pytest.mark.asyncio
    async def test_unbalanced_transaction_rejected(self, async_session: AsyncSession) -> None:
        acc_repo = AccountRepository(async_session)
        ledger_repo = LedgerRepository(async_session)

        acc_cust = await acc_repo.create(
            AccountCreate(
                account_number="1010-CUST-UNBAL",
                account_type=AccountType.CUSTOMER,
                currency=Currency.USD,
                owner_type="CUSTOMER",
            )
        )
        acc_merch = await acc_repo.create(
            AccountCreate(
                account_number="2010-MERCH-UNBAL",
                account_type=AccountType.MERCHANT,
                currency=Currency.USD,
                owner_type="MERCHANT",
            )
        )

        # Debits = 10000, Credits = 9000 (discrepancy of 1000)
        # Note: Pydantic schema will catch this at model validation if we instantiate LedgerTransactionCreate,
        # but let's test repository method directly with entries that violate parity:
        class FakeTx:
            reference = "tx_unbalanced"
            description = "Unbalanced"
            currency = Currency.USD
            correlation_id = "corr_fail"
            causation_id = None
            metadata = None
            entries = [
                LedgerEntryInput(
                    account_id=acc_cust.id,
                    direction=EntryDirection.DEBIT,
                    amount_minor=10000,
                    currency=Currency.USD,
                ),
                LedgerEntryInput(
                    account_id=acc_merch.id,
                    direction=EntryDirection.CREDIT,
                    amount_minor=9000,
                    currency=Currency.USD,
                ),
            ]

        with pytest.raises(LedgerUnbalancedError, match="Ledger transaction unbalanced"):
            await ledger_repo.post_transaction(FakeTx(), correlation_id="corr_fail")

    @pytest.mark.asyncio
    async def test_currency_mismatch_rejected(self, async_session: AsyncSession) -> None:
        acc_repo = AccountRepository(async_session)
        ledger_repo = LedgerRepository(async_session)

        acc_usd = await acc_repo.create(
            AccountCreate(
                account_number="1010-USD",
                account_type=AccountType.CUSTOMER,
                currency=Currency.USD,
                owner_type="CUSTOMER",
            )
        )
        acc_inr = await acc_repo.create(
            AccountCreate(
                account_number="2010-INR",
                account_type=AccountType.MERCHANT,
                currency=Currency.INR,
                owner_type="MERCHANT",
            )
        )

        # Attempt to pass INR entry to USD account
        tx_in = LedgerTransactionCreate(
            reference="tx_currency_mismatch",
            description="Currency mismatch test",
            currency=Currency.USD,
            entries=[
                LedgerEntryInput(
                    account_id=acc_usd.id,
                    direction=EntryDirection.DEBIT,
                    amount_minor=5000,
                    currency=Currency.USD,
                ),
                LedgerEntryInput(
                    account_id=acc_inr.id,
                    direction=EntryDirection.CREDIT,
                    amount_minor=5000,
                    currency=Currency.USD,  # trying to post USD to INR account
                ),
            ],
        )

        with pytest.raises(AccountCurrencyMismatchError, match="does not match account currency"):
            await ledger_repo.post_transaction(tx_in, correlation_id="corr_err")
