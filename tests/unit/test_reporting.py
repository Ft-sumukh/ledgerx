"""
Unit tests for FinancialReportingService.
Mathematically verifies:
  1. Trial Balance parity: sum(Debits) == sum(Credits).
  2. Balance Sheet equation: Assets == Liabilities + Equity.
  3. Income Statement: Net Income == Revenue - Expenses.
  4. Account Statement: Chronological running balance tracking.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.database.base import Base
from packages.database.repository import AccountRepository
from packages.database.schemas import AccountCreate, LedgerEntryInput, LedgerTransactionCreate
from packages.shared_types.money import AccountCategory, AccountType, Currency, EntryDirection
from services.ledger.reports import FinancialReportingService
from services.ledger.service import LedgerService


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


class TestFinancialReports:
    @pytest.mark.asyncio
    async def test_trial_balance_mathematical_parity(self, session: AsyncSession) -> None:
        ledger_service = LedgerService(session)
        reporting_service = FinancialReportingService(session)
        acc_repo = AccountRepository(session)

        # 1. Setup accounts
        acc_cash = await acc_repo.create(
            AccountCreate(account_number="1010-CASH", account_type=AccountType.PLATFORM, category=AccountCategory.ASSET, currency=Currency.USD, owner_type="PLATFORM")
        )
        acc_rec = await acc_repo.create(
            AccountCreate(account_number="1020-RECEIVABLE", account_type=AccountType.CUSTOMER, category=AccountCategory.ASSET, currency=Currency.USD, owner_type="CUSTOMER")
        )
        acc_pay = await acc_repo.create(
            AccountCreate(account_number="2010-PAYABLE", account_type=AccountType.MERCHANT, category=AccountCategory.LIABILITY, currency=Currency.USD, owner_type="MERCHANT")
        )
        acc_rev = await acc_repo.create(
            AccountCreate(account_number="4010-REVENUE", account_type=AccountType.FEES, category=AccountCategory.REVENUE, currency=Currency.USD, owner_type="PLATFORM")
        )

        # 2. Post multi-legged transactions
        # Transaction 1: Customer payment of $100 -> Cash +100, Merchant Payable +95, Revenue +5
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_sale_01",
                description="Sale with fee",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_cash.id, direction=EntryDirection.DEBIT, amount_minor=10000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_pay.id, direction=EntryDirection.CREDIT, amount_minor=9500, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_rev.id, direction=EntryDirection.CREDIT, amount_minor=500, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_rep_1",
        )

        # Transaction 2: Transfer $20 from cash to receivable
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_transfer_02",
                description="Inter-account transfer",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_rec.id, direction=EntryDirection.DEBIT, amount_minor=2000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_cash.id, direction=EntryDirection.CREDIT, amount_minor=2000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_rep_2",
        )

        # 3. Generate Trial Balance
        tb = await reporting_service.generate_trial_balance(currency=Currency.USD)

        assert tb.is_balanced is True
        assert tb.discrepancy_minor == 0
        assert tb.total_debits_minor == tb.total_credits_minor
        assert tb.total_debits_minor == 12000
        assert len(tb.accounts) == 4

    @pytest.mark.asyncio
    async def test_balance_sheet_accounting_equation(self, session: AsyncSession) -> None:
        ledger_service = LedgerService(session)
        reporting_service = FinancialReportingService(session)
        acc_repo = AccountRepository(session)

        # Create Asset, Liability, and Equity accounts
        acc_asset = await acc_repo.create(
            AccountCreate(account_number="1010-ASSET", account_type=AccountType.PLATFORM, category=AccountCategory.ASSET, currency=Currency.USD, owner_type="PLATFORM")
        )
        acc_liab = await acc_repo.create(
            AccountCreate(account_number="2010-LIAB", account_type=AccountType.MERCHANT, category=AccountCategory.LIABILITY, currency=Currency.USD, owner_type="MERCHANT")
        )
        acc_eq = await acc_repo.create(
            AccountCreate(account_number="3010-EQUITY", account_type=AccountType.PLATFORM, category=AccountCategory.EQUITY, currency=Currency.USD, owner_type="PLATFORM")
        )

        # Post transaction: Contributed capital + Liability:
        # Debit Asset $1000, Credit Liability $400, Credit Equity $600
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_funding",
                description="Initial funding and loan",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_asset.id, direction=EntryDirection.DEBIT, amount_minor=100000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_liab.id, direction=EntryDirection.CREDIT, amount_minor=40000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_eq.id, direction=EntryDirection.CREDIT, amount_minor=60000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_bs",
        )

        bs = await reporting_service.generate_balance_sheet(currency=Currency.USD)

        assert bs.is_balanced is True
        assert bs.variance_minor == 0
        assert bs.total_assets_minor == 100000
        assert bs.total_liabilities_and_equity_minor == 100000
        assert bs.assets.total_minor == 100000
        assert bs.liabilities.total_minor == 40000
        assert bs.equity.total_minor == 60000

    @pytest.mark.asyncio
    async def test_income_statement_net_income(self, session: AsyncSession) -> None:
        ledger_service = LedgerService(session)
        reporting_service = FinancialReportingService(session)
        acc_repo = AccountRepository(session)

        acc_cash = await acc_repo.create(
            AccountCreate(account_number="1010-BANK", account_type=AccountType.PLATFORM, category=AccountCategory.ASSET, currency=Currency.USD, owner_type="PLATFORM")
        )
        acc_rev = await acc_repo.create(
            AccountCreate(account_number="4010-FEES", account_type=AccountType.FEES, category=AccountCategory.REVENUE, currency=Currency.USD, owner_type="PLATFORM")
        )
        acc_exp = await acc_repo.create(
            AccountCreate(account_number="5010-COSTS", account_type=AccountType.PLATFORM, category=AccountCategory.EXPENSE, currency=Currency.USD, owner_type="PLATFORM")
        )

        # 1. Earn revenue: Debit Bank $500, Credit Revenue $500
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_rev_earned",
                description="Earned fee",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_cash.id, direction=EntryDirection.DEBIT, amount_minor=50000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_rev.id, direction=EntryDirection.CREDIT, amount_minor=50000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_inc_1",
        )

        # 2. Incur expense: Debit Expense $150, Credit Bank $150
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_cost_incurred",
                description="Network fee expense",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_exp.id, direction=EntryDirection.DEBIT, amount_minor=15000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_cash.id, direction=EntryDirection.CREDIT, amount_minor=15000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_inc_2",
        )

        inc = await reporting_service.generate_income_statement(currency=Currency.USD)

        assert inc.total_revenue_minor == 50000
        assert inc.total_expenses_minor == 15000
        assert inc.net_income_minor == 35000  # $350.00 profit

    @pytest.mark.asyncio
    async def test_account_statement_running_balance(self, session: AsyncSession) -> None:
        ledger_service = LedgerService(session)
        reporting_service = FinancialReportingService(session)
        acc_repo = AccountRepository(session)

        acc_client = await acc_repo.create(
            AccountCreate(account_number="1010-CLIENT", account_type=AccountType.CUSTOMER, category=AccountCategory.ASSET, currency=Currency.USD, owner_type="CUSTOMER")
        )
        acc_pool = await acc_repo.create(
            AccountCreate(account_number="2010-POOL", account_type=AccountType.MERCHANT, category=AccountCategory.LIABILITY, currency=Currency.USD, owner_type="MERCHANT")
        )

        # 3 transactions: +1000, +2500, -800
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_stmt_1",
                description="Deposit 1",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_client.id, direction=EntryDirection.DEBIT, amount_minor=1000, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_pool.id, direction=EntryDirection.CREDIT, amount_minor=1000, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_stmt_1",
        )
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_stmt_2",
                description="Deposit 2",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_client.id, direction=EntryDirection.DEBIT, amount_minor=2500, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_pool.id, direction=EntryDirection.CREDIT, amount_minor=2500, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_stmt_2",
        )
        await ledger_service.post_transaction(
            LedgerTransactionCreate(
                reference="tx_stmt_3",
                description="Withdrawal",
                currency=Currency.USD,
                entries=[
                    LedgerEntryInput(account_id=acc_client.id, direction=EntryDirection.CREDIT, amount_minor=800, currency=Currency.USD),
                    LedgerEntryInput(account_id=acc_pool.id, direction=EntryDirection.DEBIT, amount_minor=800, currency=Currency.USD),
                ],
            ),
            correlation_id="corr_stmt_3",
        )

        stmt = await reporting_service.generate_account_statement(account_id=acc_client.id)

        assert len(stmt.entries) == 3
        # Running balances: 1000, then 1000 + 2500 = 3500, then 3500 - 800 = 2700
        assert stmt.entries[0].running_balance_minor == 1000
        assert stmt.entries[1].running_balance_minor == 3500
        assert stmt.entries[2].running_balance_minor == 2700
        assert stmt.closing_balance_minor == 2700
