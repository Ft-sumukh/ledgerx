"""
Unit tests for Compensating Reversal engine in services/ledger/service.py.
Verifies GAAP/IFRS immutable reversal guarantees and algebraic net-zero cancellation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.models.entities import OutboxEvent
from packages.database.repository import AccountRepository, EntityNotFoundError
from packages.database.schemas import AccountCreate, LedgerEntryInput, LedgerTransactionCreate
from packages.shared_types.money import AccountCategory, AccountType, Currency, EntryDirection
from services.ledger.service import (
    LedgerService,
    TransactionAlreadyReversedError,
)


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


class TestCompensatingReversals:
    @pytest.mark.asyncio
    async def test_reversal_creates_exact_canceling_entries(self, session: AsyncSession) -> None:
        service = LedgerService(session)
        acc_repo = AccountRepository(session)

        # 1. Create accounts
        acc_cash = await acc_repo.create(
            AccountCreate(
                account_number="1010-CASH",
                account_type=AccountType.CUSTOMER,
                currency=Currency.USD,
                owner_type="CUSTOMER",
            )
        )
        acc_merch = await acc_repo.create(
            AccountCreate(
                account_number="2010-MERCH",
                account_type=AccountType.MERCHANT,
                currency=Currency.USD,
                owner_type="MERCHANT",
            )
        )

        # 2. Post original transaction: $100.00 (10000 cents)
        tx_orig = await service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_orig_100",
                description="Purchase item",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(
                        account_id=acc_cash.id,
                        direction=EntryDirection.CREDIT,
                        amount_minor=10000,
                        currency=Currency.USD,
                    ),
                    LedgerEntryInput(
                        account_id=acc_merch.id,
                        direction=EntryDirection.DEBIT,
                        amount_minor=10000,
                        currency=Currency.USD,
                    ),
                ],
            ),
            correlation_id="corr_orig",
        )

        # Verify balances before reversal
        bal_cash_before = await service.ledger_repo.derive_account_balance(acc_cash.id)
        bal_merch_before = await service.ledger_repo.derive_account_balance(acc_merch.id)
        assert bal_cash_before == -10000
        assert bal_merch_before == -10000

        # 3. Issue compensating reversal
        rev_tx = await service.create_compensating_reversal(
            original_reference="tx_orig_100",
            reason="Customer returned damaged merchandise",
            correlation_id="corr_rev",
        )

        assert rev_tx.id is not None
        assert rev_tx.related_transaction_id == tx_orig.id
        assert rev_tx.is_balanced() is True
        assert len(rev_tx.entries) == 2

        # Inverted direction check
        cash_leg = next(e for e in rev_tx.entries if e.account_id == acc_cash.id)
        merch_leg = next(e for e in rev_tx.entries if e.account_id == acc_merch.id)
        assert cash_leg.direction == "DEBIT"  # Was CREDIT
        assert merch_leg.direction == "CREDIT"  # Was DEBIT

        # 4. Verify balances return to exact net ZERO
        bal_cash_after = await service.ledger_repo.derive_account_balance(acc_cash.id)
        bal_merch_after = await service.ledger_repo.derive_account_balance(acc_merch.id)
        assert bal_cash_after == 0
        assert bal_merch_after == 0

        # 5. Verify original transaction status is REVERSED
        orig_reloaded = await service.ledger_repo.get_by_reference("tx_orig_100")
        assert orig_reloaded is not None
        assert orig_reloaded.status == "REVERSED"
        assert orig_reloaded.related_transaction_id == rev_tx.id

    @pytest.mark.asyncio
    async def test_reversal_of_three_legged_transaction(self, session: AsyncSession) -> None:
        service = LedgerService(session)
        acc_repo = AccountRepository(session)

        acc_cust = await acc_repo.create(
            AccountCreate(account_number="1010-3LEG-CUST", account_type=AccountType.CUSTOMER, currency=Currency.USD, owner_type="CUSTOMER")
        )
        acc_merch = await acc_repo.create(
            AccountCreate(account_number="2010-3LEG-MERCH", account_type=AccountType.MERCHANT, currency=Currency.USD, owner_type="MERCHANT")
        )
        acc_fee = await acc_repo.create(
            AccountCreate(account_number="4010-3LEG-FEE", account_type=AccountType.FEES, currency=Currency.USD, owner_type="PLATFORM")
        )

        # $100 total: Cust -10000, Merch +9500, Fee +500
        await service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_split_3leg",
                description="Split fee payment",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_cust.id, direction=EntryDirection.CREDIT, amount_minor=10000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_merch.id, direction=EntryDirection.DEBIT, amount_minor=9500, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_fee.id, direction=EntryDirection.DEBIT, amount_minor=500, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_3leg",
        )

        rev_tx = await service.create_compensating_reversal("tx_split_3leg", "Full Refund", correlation_id="corr_rev_3leg")
        assert len(rev_tx.entries) == 3
        assert rev_tx.is_balanced() is True

        # All 3 accounts must be exactly zero
        assert await service.ledger_repo.derive_account_balance(acc_cust.id) == 0
        assert await service.ledger_repo.derive_account_balance(acc_merch.id) == 0
        assert await service.ledger_repo.derive_account_balance(acc_fee.id) == 0

    @pytest.mark.asyncio
    async def test_reversal_creates_outbox_event(self, session: AsyncSession) -> None:
        service = LedgerService(session)
        acc_repo = AccountRepository(session)

        acc1 = await acc_repo.create(
            AccountCreate(account_number="1010-OB1", account_type=AccountType.CUSTOMER, currency=Currency.USD, owner_type="CUSTOMER")
        )
        acc2 = await acc_repo.create(
            AccountCreate(account_number="2010-OB2", account_type=AccountType.MERCHANT, currency=Currency.USD, owner_type="MERCHANT")
        )

        await service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_for_outbox",
                description="Outbox test",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc1.id, direction=EntryDirection.DEBIT, amount_minor=1000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc2.id, direction=EntryDirection.CREDIT, amount_minor=1000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_ob",
        )

        await service.create_compensating_reversal("tx_for_outbox", "Outbox verification", correlation_id="corr_ob_rev")

        # Query OutboxEvent table
        stmt = select(OutboxEvent).where(OutboxEvent.event_type == "TransactionReversed")
        res = await session.execute(stmt)
        events = res.scalars().all()
        assert len(events) >= 1
        event = events[-1]
        payload = json.loads(event.payload_json)
        assert payload["original_reference"] == "tx_for_outbox"
        assert payload["reason"] == "Outbox verification"

    @pytest.mark.asyncio
    async def test_point_in_time_balance_derivation(self, session: AsyncSession) -> None:
        service = LedgerService(session)
        acc_repo = AccountRepository(session)

        acc = await acc_repo.create(
            AccountCreate(account_number="1010-PIT", account_type=AccountType.CUSTOMER, currency=Currency.USD, owner_type="CUSTOMER")
        )
        acc_other = await acc_repo.create(
            AccountCreate(account_number="2010-PIT-OTHER", account_type=AccountType.MERCHANT, currency=Currency.USD, owner_type="MERCHANT")
        )

        t_before = datetime.now(timezone.utc) - timedelta(hours=1)

        await service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_pit_1",
                description="Deposit",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc.id, direction=EntryDirection.DEBIT, amount_minor=5000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_other.id, direction=EntryDirection.CREDIT, amount_minor=5000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_pit",
        )

        t_after = datetime.now(timezone.utc) + timedelta(hours=1)

        # Balance before transaction must be 0
        bal_before = await service.get_point_in_time_balance(acc.id, as_of=t_before)
        assert bal_before == 0

        # Balance after transaction must be 5000
        bal_after = await service.get_point_in_time_balance(acc.id, as_of=t_after)
        assert bal_after == 5000

    @pytest.mark.asyncio
    async def test_reversing_already_reversed_transaction_raises(self, session: AsyncSession) -> None:
        service = LedgerService(session)
        acc_repo = AccountRepository(session)

        acc1 = await acc_repo.create(
            AccountCreate(
                account_number="1010-A",
                account_type=AccountType.CUSTOMER,
                currency=Currency.USD,
                owner_type="CUSTOMER",
            )
        )
        acc2 = await acc_repo.create(
            AccountCreate(
                account_number="2010-B",
                account_type=AccountType.MERCHANT,
                currency=Currency.USD,
                owner_type="MERCHANT",
            )
        )

        await service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_double_rev",
                description="Original payment",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc1.id, direction=EntryDirection.DEBIT, amount_minor=2000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc2.id, direction=EntryDirection.CREDIT, amount_minor=2000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_1",
        )

        # First reversal succeeds
        await service.create_compensating_reversal("tx_double_rev", "Reason 1", correlation_id="corr_rev1")

        # Second reversal must fail
        with pytest.raises(TransactionAlreadyReversedError, match="already been reversed"):
            await service.create_compensating_reversal("tx_double_rev", "Reason 2", correlation_id="corr_rev2")

    @pytest.mark.asyncio
    async def test_reversing_nonexistent_transaction_raises_404(self, session: AsyncSession) -> None:
        service = LedgerService(session)
        with pytest.raises(EntityNotFoundError, match="not found"):
            await service.create_compensating_reversal("tx_ghost", "Reason", correlation_id="corr_ghost")
