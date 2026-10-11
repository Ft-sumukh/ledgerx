"""
LEDGER-ORBIT: Ledger Domain Service
===================================
High-level financial orchestrator handling multi-legged journal posting,
compensating reversals, point-in-time balance evaluation, and Chart of Accounts templates.

CONSTITUTIONAL RULES:
  - Ledger Immutability: Posted entries are NEVER updated or deleted.
  - Corrections occur strictly through balanced compensating reversals.
  - Zero floating-point arithmetic.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.database.models.entities import Account, OutboxEvent
from packages.database.models.ledger import LedgerEntry, LedgerTransaction
from packages.database.repository import (
    AccountRepository,
    EntityNotFoundError,
    LedgerError,
    LedgerRepository,
)
from packages.database.schemas import (
    AccountCreate,
    LedgerEntryInput,
    LedgerTransactionCreate,
)
from packages.logging.logger import get_logger
from packages.shared_types.money import (
    AccountCategory,
    AccountType,
    Currency,
    EntryDirection,
    NormalBalance,
)

logger = get_logger(__name__)


class TransactionAlreadyReversedError(LedgerError):
    """Raised when attempting to reverse a transaction that has already been reversed."""


class TransactionNotReversibleError(LedgerError):
    """Raised when attempting to reverse a non-POSTED transaction."""


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ledger_repo = LedgerRepository(session)
        self.account_repo = AccountRepository(session)

    async def post_transaction(
        self,
        tx_in: LedgerTransactionCreate,
        correlation_id: str,
    ) -> LedgerTransaction:
        """Post a balanced multi-legged transaction."""
        return await self.ledger_repo.post_transaction(tx_in, correlation_id=correlation_id)

    async def create_compensating_reversal(
        self,
        original_reference: str,
        reason: str,
        correlation_id: str,
        reversal_reference: Optional[str] = None,
    ) -> LedgerTransaction:
        """
        Create an exact compensating reversal transaction under GAAP/IFRS rules.
        Reverses all entry legs (DEBIT -> CREDIT, CREDIT -> DEBIT), negating the original balance impact.
        Marks original transaction as REVERSED and links via related_transaction_id.
        """
        # 1. Fetch original transaction
        original_tx = await self.ledger_repo.get_by_reference(original_reference)
        if not original_tx:
            raise EntityNotFoundError(f"Original transaction '{original_reference}' not found")

        if original_tx.status == "REVERSED":
            raise TransactionAlreadyReversedError(
                f"Transaction '{original_reference}' has already been reversed"
            )
        if original_tx.status != "POSTED":
            raise TransactionNotReversibleError(
                f"Only POSTED transactions can be reversed. Status is '{original_tx.status}'"
            )

        # 2. Build inverted entry legs
        rev_entries: List[LedgerEntryInput] = []
        for leg in original_tx.entries:
            inverted_dir = (
                EntryDirection.CREDIT if leg.direction == "DEBIT" else EntryDirection.DEBIT
            )
            rev_entries.append(
                LedgerEntryInput(
                    account_id=leg.account_id,
                    direction=inverted_dir,
                    amount_minor=leg.amount_minor,
                    currency=Currency(leg.currency),
                )
            )

        # 3. Create reversal reference
        rev_ref = reversal_reference or f"rev_{original_reference}_{uuid.uuid4().hex[:8]}"

        rev_tx_create = LedgerTransactionCreate(
            reference=rev_ref,
            description=f"Reversal of {original_reference}: {reason}",
            currency=Currency(original_tx.currency),
            entries=rev_entries,
            correlation_id=correlation_id,
            causation_id=original_tx.id,
            metadata={
                "reversal_reason": reason,
                "original_reference": original_reference,
                "original_transaction_id": original_tx.id,
            },
        )

        # 4. Post the reversal transaction
        rev_tx = await self.ledger_repo.post_transaction(rev_tx_create, correlation_id=correlation_id)

        # 5. Link and update statuses
        rev_tx.related_transaction_id = original_tx.id
        original_tx.status = "REVERSED"
        original_tx.related_transaction_id = rev_tx.id

        # 6. Publish OutboxEvent for reversal
        outbox = OutboxEvent(
            id=str(uuid.uuid4()),
            event_type="TransactionReversed",
            aggregate_type="LedgerTransaction",
            aggregate_id=original_tx.id,
            status="PENDING",
            payload_json=json.dumps({
                "original_transaction_id": original_tx.id,
                "original_reference": original_reference,
                "reversal_transaction_id": rev_tx.id,
                "reversal_reference": rev_ref,
                "reason": reason,
            }),
            correlation_id=correlation_id,
        )
        self.session.add(outbox)

        await self.session.flush()
        logger.info(
            "Transaction reversed successfully",
            extra={
                "original_reference": original_reference,
                "reversal_reference": rev_ref,
                "correlation_id": correlation_id,
            },
        )
        return rev_tx

    async def get_point_in_time_balance(
        self,
        account_id: str,
        as_of: datetime,
    ) -> int:
        """
        Calculate account balance as of a historical timestamp by summing entries posted <= as_of.
        """
        acc = await self.account_repo.get_by_id(account_id)
        if not acc:
            raise EntityNotFoundError(f"Account '{account_id}' not found")

        stmt = (
            select(LedgerEntry)
            .join(LedgerTransaction)
            .where(
                LedgerEntry.account_id == account_id,
                LedgerTransaction.posted_at <= as_of,
            )
        )
        res = await self.session.execute(stmt)
        entries = res.scalars().all()

        balance = 0
        for e in entries:
            if acc.normal_balance == NormalBalance.DEBIT.value:
                delta = e.amount_minor if e.direction == "DEBIT" else -e.amount_minor
            else:
                delta = e.amount_minor if e.direction == "CREDIT" else -e.amount_minor
            balance += delta

        return balance

    async def seed_default_chart_of_accounts(
        self,
        tenant_id: str,
        currency: Currency = Currency.USD,
    ) -> List[Account]:
        """
        Seed standard default Chart of Accounts hierarchy for a tenant.
        Covers the 5 fundamental categories (Asset, Liability, Equity, Revenue, Expense).
        """
        coa_templates = [
            # 1000 - ASSETS
            ("1010", "Operating Cash", AccountType.PLATFORM, AccountCategory.ASSET),
            ("1020", "Settlement Clearing", AccountType.SETTLEMENT, AccountCategory.ASSET),
            ("1030", "Reserve Fund", AccountType.RESERVE, AccountCategory.ASSET),
            # 2000 - LIABILITIES
            ("2010", "Merchant Payables", AccountType.MERCHANT, AccountCategory.LIABILITY),
            ("2020", "Customer Deposits", AccountType.CUSTOMER, AccountCategory.LIABILITY),
            # 3000 - EQUITY
            ("3010", "Retained Earnings", AccountType.PLATFORM, AccountCategory.EQUITY),
            # 4000 - REVENUE
            ("4010", "Processing Fee Revenue", AccountType.FEES, AccountCategory.REVENUE),
            ("4020", "Platform Subscription Revenue", AccountType.FEES, AccountCategory.REVENUE),
            # 5000 - EXPENSES
            ("5010", "Card Network Assessment Fees", AccountType.PLATFORM, AccountCategory.EXPENSE),
            ("5020", "Chargeback Loss Provisions", AccountType.PLATFORM, AccountCategory.EXPENSE),
        ]

        created_accounts: List[Account] = []
        for code, name, acc_type, category in coa_templates:
            acc_num = f"{code}-{tenant_id}-{currency.value}"
            existing = await self.account_repo.get_by_number(acc_num)
            if existing:
                created_accounts.append(existing)
                continue

            acc = await self.account_repo.create(
                AccountCreate(
                    account_number=acc_num,
                    account_type=acc_type,
                    category=category,
                    currency=currency,
                    owner_type="PLATFORM",
                    owner_id=tenant_id,
                )
            )
            created_accounts.append(acc)

        return created_accounts
