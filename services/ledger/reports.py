"""
LEDGER-ORBIT: Financial Reporting & Statements Service
======================================================
Produces GAAP/IFRS-compliant financial statements and mathematical invariant verifications:
  - Trial Balance (sum of debits == sum of credits across all accounts)
  - Balance Sheet (Assets = Liabilities + Equity)
  - Income Statement / P&L (Net Income = Revenue - Expenses)
  - General Ledger Account Statement (chronological running balance ledger)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.database.models.entities import Account
from packages.database.models.ledger import LedgerEntry, LedgerTransaction
from packages.database.repository import AccountRepository, EntityNotFoundError
from packages.database.schemas import (
    AccountStatementEntry,
    AccountStatementReport,
    BalanceSheetReport,
    CategorySummary,
    IncomeStatementReport,
    TrialBalanceItem,
    TrialBalanceReport,
)
from packages.logging.logger import get_logger
from packages.shared_types.money import (
    AccountCategory,
    Currency,
    EntryDirection,
    NormalBalance,
)

logger = get_logger(__name__)


class FinancialReportingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.account_repo = AccountRepository(session)

    async def generate_trial_balance(
        self,
        as_of: Optional[datetime] = None,
        currency: Optional[Currency] = None,
    ) -> TrialBalanceReport:
        """
        Generate a Trial Balance report verifying the fundamental invariant:
        Total Debit Entries == Total Credit Entries.
        """
        as_of_time = as_of or datetime.now(timezone.utc)

        # 1. Fetch all accounts
        acc_stmt = select(Account)
        if currency:
            acc_stmt = acc_stmt.where(Account.currency == currency.value)
        acc_res = await self.session.execute(acc_stmt)
        accounts = acc_res.scalars().all()

        items: List[TrialBalanceItem] = []
        total_debits = 0
        total_credits = 0

        for acc in accounts:
            # Fetch entries on or before as_of_time
            stmt = (
                select(LedgerEntry)
                .join(LedgerTransaction)
                .where(
                    LedgerEntry.account_id == acc.id,
                    LedgerTransaction.posted_at <= as_of_time,
                )
            )
            entries_res = await self.session.execute(stmt)
            entries = entries_res.scalars().all()

            acc_debits = sum(e.amount_minor for e in entries if e.direction == "DEBIT")
            acc_credits = sum(e.amount_minor for e in entries if e.direction == "CREDIT")

            total_debits += acc_debits
            total_credits += acc_credits

            # Compute net balance according to normal balance convention
            if acc.normal_balance == NormalBalance.DEBIT.value:
                net_bal = acc_debits - acc_credits
            else:
                net_bal = acc_credits - acc_debits

            items.append(
                TrialBalanceItem(
                    account_id=acc.id,
                    account_number=acc.account_number,
                    category=acc.category,
                    account_type=acc.account_type,
                    currency=acc.currency,
                    normal_balance=acc.normal_balance,
                    total_debit_minor=acc_debits,
                    total_credit_minor=acc_credits,
                    net_balance_minor=net_bal,
                )
            )

        discrepancy = total_debits - total_credits
        is_balanced = discrepancy == 0

        return TrialBalanceReport(
            as_of=as_of_time,
            currency=currency.value if currency else "ALL",
            accounts=items,
            total_debits_minor=total_debits,
            total_credits_minor=total_credits,
            is_balanced=is_balanced,
            discrepancy_minor=discrepancy,
        )

    async def generate_balance_sheet(
        self,
        as_of: Optional[datetime] = None,
        currency: Optional[Currency] = None,
    ) -> BalanceSheetReport:
        """
        Generate a Balance Sheet verifying the fundamental equation:
        Assets = Liabilities + Equity.
        """
        tb = await self.generate_trial_balance(as_of=as_of, currency=currency)

        assets_list = [a for a in tb.accounts if a.category == AccountCategory.ASSET.value]
        liabilities_list = [a for a in tb.accounts if a.category == AccountCategory.LIABILITY.value]
        equity_list = [a for a in tb.accounts if a.category == AccountCategory.EQUITY.value]

        total_assets = sum(a.net_balance_minor for a in assets_list)
        total_liabilities = sum(a.net_balance_minor for a in liabilities_list)
        total_equity = sum(a.net_balance_minor for a in equity_list)

        total_liab_and_equity = total_liabilities + total_equity
        variance = total_assets - total_liab_and_equity
        is_balanced = variance == 0

        return BalanceSheetReport(
            as_of=tb.as_of,
            currency=tb.currency,
            assets=CategorySummary(
                category="ASSETS",
                total_minor=total_assets,
                accounts=assets_list,
            ),
            liabilities=CategorySummary(
                category="LIABILITIES",
                total_minor=total_liabilities,
                accounts=liabilities_list,
            ),
            equity=CategorySummary(
                category="EQUITY",
                total_minor=total_equity,
                accounts=equity_list,
            ),
            total_assets_minor=total_assets,
            total_liabilities_and_equity_minor=total_liab_and_equity,
            is_balanced=is_balanced,
            variance_minor=variance,
        )

    async def generate_income_statement(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        currency: Optional[Currency] = None,
    ) -> IncomeStatementReport:
        """
        Generate an Income Statement / Profit & Loss report:
        Net Income = Revenue - Expenses.
        """
        to_time = to_date or datetime.now(timezone.utc)

        acc_stmt = select(Account).where(
            Account.category.in_([AccountCategory.REVENUE.value, AccountCategory.EXPENSE.value])
        )
        if currency:
            acc_stmt = acc_stmt.where(Account.currency == currency.value)
        acc_res = await self.session.execute(acc_stmt)
        accounts = acc_res.scalars().all()

        revenue_items: List[TrialBalanceItem] = []
        expense_items: List[TrialBalanceItem] = []

        total_revenue = 0
        total_expense = 0

        for acc in accounts:
            stmt = (
                select(LedgerEntry)
                .join(LedgerTransaction)
                .where(
                    LedgerEntry.account_id == acc.id,
                    LedgerTransaction.posted_at <= to_time,
                )
            )
            if from_date:
                stmt = stmt.where(LedgerTransaction.posted_at >= from_date)

            entries_res = await self.session.execute(stmt)
            entries = entries_res.scalars().all()

            acc_debits = sum(e.amount_minor for e in entries if e.direction == "DEBIT")
            acc_credits = sum(e.amount_minor for e in entries if e.direction == "CREDIT")

            if acc.category == AccountCategory.REVENUE.value:
                net_bal = acc_credits - acc_debits  # Normal credit
                total_revenue += net_bal
                revenue_items.append(
                    TrialBalanceItem(
                        account_id=acc.id,
                        account_number=acc.account_number,
                        category=acc.category,
                        account_type=acc.account_type,
                        currency=acc.currency,
                        normal_balance=acc.normal_balance,
                        total_debit_minor=acc_debits,
                        total_credit_minor=acc_credits,
                        net_balance_minor=net_bal,
                    )
                )
            else:
                net_bal = acc_debits - acc_credits  # Normal debit
                total_expense += net_bal
                expense_items.append(
                    TrialBalanceItem(
                        account_id=acc.id,
                        account_number=acc.account_number,
                        category=acc.category,
                        account_type=acc.account_type,
                        currency=acc.currency,
                        normal_balance=acc.normal_balance,
                        total_debit_minor=acc_debits,
                        total_credit_minor=acc_credits,
                        net_balance_minor=net_bal,
                    )
                )

        net_income = total_revenue - total_expense

        return IncomeStatementReport(
            from_date=from_date,
            to_date=to_time,
            currency=currency.value if currency else "ALL",
            revenue=CategorySummary(
                category="REVENUE",
                total_minor=total_revenue,
                accounts=revenue_items,
            ),
            expenses=CategorySummary(
                category="EXPENSES",
                total_minor=total_expense,
                accounts=expense_items,
            ),
            total_revenue_minor=total_revenue,
            total_expenses_minor=total_expense,
            net_income_minor=net_income,
        )

    async def generate_account_statement(
        self,
        account_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> AccountStatementReport:
        """
        Generate a detailed chronological statement of entries for an account with running balance.
        """
        acc = await self.account_repo.get_by_id(account_id)
        if not acc:
            raise EntityNotFoundError(f"Account '{account_id}' not found")

        # 1. Calculate opening balance before from_date
        opening_balance = 0
        if from_date:
            prior_stmt = (
                select(LedgerEntry)
                .join(LedgerTransaction)
                .where(
                    LedgerEntry.account_id == account_id,
                    LedgerTransaction.posted_at < from_date,
                )
            )
            prior_res = await self.session.execute(prior_stmt)
            prior_entries = prior_res.scalars().all()
            for p in prior_entries:
                if acc.normal_balance == NormalBalance.DEBIT.value:
                    delta = p.amount_minor if p.direction == "DEBIT" else -p.amount_minor
                else:
                    delta = p.amount_minor if p.direction == "CREDIT" else -p.amount_minor
                opening_balance += delta

        # 2. Fetch period entries ordered chronologically
        stmt = (
            select(LedgerEntry, LedgerTransaction)
            .join(LedgerTransaction)
            .where(LedgerEntry.account_id == account_id)
            .order_by(LedgerTransaction.posted_at.asc(), LedgerEntry.sequence.asc())
        )
        if from_date:
            stmt = stmt.where(LedgerTransaction.posted_at >= from_date)
        if to_date:
            stmt = stmt.where(LedgerTransaction.posted_at <= to_date)

        res = await self.session.execute(stmt)
        rows = res.all()

        current_running = opening_balance
        statement_entries: List[AccountStatementEntry] = []

        for entry, tx in rows:
            if acc.normal_balance == NormalBalance.DEBIT.value:
                delta = entry.amount_minor if entry.direction == "DEBIT" else -entry.amount_minor
            else:
                delta = entry.amount_minor if entry.direction == "CREDIT" else -entry.amount_minor
            current_running += delta

            statement_entries.append(
                AccountStatementEntry(
                    entry_id=entry.id,
                    transaction_id=tx.id,
                    transaction_reference=tx.reference,
                    posted_at=tx.posted_at,
                    description=tx.description,
                    direction=entry.direction,
                    amount_minor=entry.amount_minor,
                    running_balance_minor=current_running,
                )
            )

        return AccountStatementReport(
            account_id=acc.id,
            account_number=acc.account_number,
            account_type=acc.account_type,
            category=acc.category,
            currency=acc.currency,
            normal_balance=acc.normal_balance,
            opening_balance_minor=opening_balance,
            closing_balance_minor=current_running,
            entries=statement_entries,
        )
