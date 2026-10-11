"""
LEDGER-ORBIT: Database Repositories & Transaction Pipeline
===========================================================
High-integrity repositories enforcing double-entry invariants, atomic posting,
and transactional outbox event publishing.

CONSTITUTIONAL RULES:
  - sum(Debits) == sum(Credits) strictly enforced before commit.
  - Zero floats: all balance adjustments use signed integer minor units.
  - OutboxEvent written in the SAME database transaction as the financial state change.
"""

from __future__ import annotations

import json
import uuid
from typing import List, Optional, Sequence
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.database.models.entities import (
    Account,
    Customer,
    IdempotencyRecord,
    Merchant,
    OutboxEvent,
    PaymentIntent,
)
from packages.database.models.ledger import LedgerEntry, LedgerTransaction
from packages.database.schemas import (
    AccountCreate,
    CustomerCreate,
    LedgerTransactionCreate,
    MerchantCreate,
    PaymentIntentCreate,
)
from packages.logging.logger import get_logger
from packages.shared_types.money import (
    AccountType,
    EntryDirection,
    NormalBalance,
    PaymentStatus,
)

logger = get_logger(__name__)


class LedgerError(Exception):
    """Base error for ledger operations."""


class LedgerUnbalancedError(LedgerError):
    """Raised when sum(Debits) != sum(Credits) in a transaction."""


class EntityNotFoundError(LedgerError):
    """Raised when a requested entity does not exist."""


class AccountCurrencyMismatchError(LedgerError):
    """Raised when entry currency does not match account currency."""


class DuplicateEntityError(LedgerError):
    """Raised on unique constraint conflict."""


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: CustomerCreate) -> Customer:
        customer = Customer(
            id=str(uuid.uuid4()),
            external_id=data.external_id,
            email=data.email,
            name=data.name,
            status="ACTIVE",
            metadata_json=json.dumps(data.metadata) if data.metadata else None,
        )
        self.session.add(customer)
        await self.session.flush()
        logger.info("Customer created", extra={"customer_id": customer.id, "email": customer.email})
        return customer

    async def get_by_id(self, customer_id: str) -> Optional[Customer]:
        stmt = select(Customer).where(Customer.id == customer_id).options(selectinload(Customer.accounts))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[Customer]:
        stmt = select(Customer).where(Customer.external_id == external_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[Customer]:
        stmt = select(Customer).limit(limit).offset(offset).order_by(Customer.created_at.desc())
        res = await self.session.execute(stmt)
        return res.scalars().all()


class MerchantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: MerchantCreate) -> Merchant:
        merchant = Merchant(
            id=str(uuid.uuid4()),
            external_id=data.external_id,
            business_name=data.business_name,
            settlement_currency=data.settlement_currency.value,
            status="ACTIVE",
            metadata_json=json.dumps(data.metadata) if data.metadata else None,
        )
        self.session.add(merchant)
        await self.session.flush()
        logger.info("Merchant created", extra={"merchant_id": merchant.id, "business_name": merchant.business_name})
        return merchant

    async def get_by_id(self, merchant_id: str) -> Optional[Merchant]:
        stmt = select(Merchant).where(Merchant.id == merchant_id).options(selectinload(Merchant.accounts))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self, limit: int = 50, offset: int = 0) -> Sequence[Merchant]:
        stmt = select(Merchant).limit(limit).offset(offset).order_by(Merchant.created_at.desc())
        res = await self.session.execute(stmt)
        return res.scalars().all()


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _determine_normal_balance(self, account_type: AccountType) -> str:
        # Asset / Customer accounts are normal DEBIT
        # Liability / Equity / Revenue / Merchant accounts are normal CREDIT
        if account_type in (AccountType.CUSTOMER, AccountType.RESERVE):
            return NormalBalance.DEBIT.value
        return NormalBalance.CREDIT.value

    async def create(self, data: AccountCreate) -> Account:
        normal_bal = self._determine_normal_balance(data.account_type)
        account = Account(
            id=str(uuid.uuid4()),
            account_number=data.account_number,
            account_type=data.account_type.value,
            normal_balance=normal_bal,
            currency=data.currency.value,
            owner_type=data.owner_type,
            owner_id=data.owner_id,
            customer_id=data.customer_id,
            merchant_id=data.merchant_id,
            status="ACTIVE",
            current_balance_minor=0,
        )
        self.session.add(account)
        await self.session.flush()
        logger.info(
            "Account created",
            extra={
                "account_id": account.id,
                "account_number": account.account_number,
                "currency": account.currency,
            },
        )
        return account

    async def get_by_id(self, account_id: str) -> Optional[Account]:
        stmt = select(Account).where(Account.id == account_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_number(self, account_number: str) -> Optional[Account]:
        stmt = select(Account).where(Account.account_number == account_number)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[Account]:
        stmt = select(Account).limit(limit).offset(offset).order_by(Account.created_at.desc())
        res = await self.session.execute(stmt)
        return res.scalars().all()


class LedgerRepository:
    """
    Implements the core double-entry transaction posting pipeline.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def post_transaction(
        self,
        tx_in: LedgerTransactionCreate,
        correlation_id: str,
    ) -> LedgerTransaction:
        """
        Atomically post a multi-legged ledger transaction.
        Enforces sum(Debits) == sum(Credits), updates account balances,
        and creates an OutboxEvent in the same transaction.
        """
        # 1. Enforce mathematical double-entry balance invariant
        debits = sum(e.amount_minor for e in tx_in.entries if e.direction == EntryDirection.DEBIT)
        credits = sum(e.amount_minor for e in tx_in.entries if e.direction == EntryDirection.CREDIT)
        if debits != credits:
            raise LedgerUnbalancedError(
                f"Ledger transaction unbalanced! Debits ({debits}) != Credits ({credits}). Discrepancy: {debits - credits}"
            )
        if len(tx_in.entries) < 2:
            raise LedgerUnbalancedError("Transaction must have at least 2 legs")

        # 2. Check and load all accounts
        account_ids = [e.account_id for e in tx_in.entries]
        stmt = select(Account).where(Account.id.in_(account_ids))
        res = await self.session.execute(stmt)
        accounts_by_id = {acc.id: acc for acc in res.scalars().all()}

        for entry in tx_in.entries:
            if entry.account_id not in accounts_by_id:
                raise EntityNotFoundError(f"Account {entry.account_id} not found")
            acc = accounts_by_id[entry.account_id]
            if acc.currency != entry.currency.value:
                raise AccountCurrencyMismatchError(
                    f"Entry currency {entry.currency} does not match account currency {acc.currency}"
                )

        # 3. Create the parent LedgerTransaction
        tx_id = str(uuid.uuid4())
        corr_id = tx_in.correlation_id or correlation_id
        tx = LedgerTransaction(
            id=tx_id,
            reference=tx_in.reference,
            status="POSTED",
            description=tx_in.description,
            currency=tx_in.currency.value,
            correlation_id=corr_id,
            causation_id=tx_in.causation_id,
            metadata_json=json.dumps(tx_in.metadata) if tx_in.metadata else None,
        )
        self.session.add(tx)

        # 4. Create child LedgerEntry legs and apply balance delta to Accounts
        for idx, entry_in in enumerate(tx_in.entries):
            entry = LedgerEntry(
                id=str(uuid.uuid4()),
                transaction_id=tx_id,
                account_id=entry_in.account_id,
                direction=entry_in.direction.value,
                amount_minor=entry_in.amount_minor,
                currency=entry_in.currency.value,
                sequence=idx,
            )
            self.session.add(entry)

            # Calculate balance impact based on normal balance
            acc = accounts_by_id[entry_in.account_id]
            if acc.normal_balance == NormalBalance.DEBIT.value:
                # DEBIT increases, CREDIT decreases
                delta = entry_in.amount_minor if entry_in.direction == EntryDirection.DEBIT else -entry_in.amount_minor
            else:
                # CREDIT increases, DEBIT decreases
                delta = entry_in.amount_minor if entry_in.direction == EntryDirection.CREDIT else -entry_in.amount_minor

            acc.current_balance_minor += delta

        # 5. Write OutboxEvent atomically
        outbox = OutboxEvent(
            id=str(uuid.uuid4()),
            event_type="TransactionPosted",
            aggregate_type="LedgerTransaction",
            aggregate_id=tx_id,
            status="PENDING",
            payload_json=json.dumps({
                "transaction_id": tx_id,
                "reference": tx_in.reference,
                "currency": tx_in.currency.value,
                "total_minor": debits,
                "legs_count": len(tx_in.entries),
            }),
            correlation_id=corr_id,
        )
        self.session.add(outbox)

        await self.session.flush()
        logger.info(
            "Ledger transaction posted",
            extra={
                "transaction_id": tx_id,
                "reference": tx.reference,
                "amount_minor": debits,
                "legs": len(tx_in.entries),
            },
        )

        # Re-query with entries loaded for returning
        query = select(LedgerTransaction).where(LedgerTransaction.id == tx_id).options(selectinload(LedgerTransaction.entries))
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_by_reference(self, reference: str) -> Optional[LedgerTransaction]:
        stmt = select(LedgerTransaction).where(LedgerTransaction.reference == reference).options(selectinload(LedgerTransaction.entries))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_transactions(self, limit: int = 50, offset: int = 0) -> Sequence[LedgerTransaction]:
        stmt = select(LedgerTransaction).limit(limit).offset(offset).order_by(LedgerTransaction.posted_at.desc()).options(selectinload(LedgerTransaction.entries))
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def derive_account_balance(self, account_id: str) -> int:
        """
        Computes exact account balance by summing all historical LedgerEntry legs from first principles.
        """
        acc_stmt = select(Account).where(Account.id == account_id)
        acc_res = await self.session.execute(acc_stmt)
        acc = acc_res.scalar_one_or_none()
        if not acc:
            raise EntityNotFoundError(f"Account {account_id} not found")

        entries_stmt = select(LedgerEntry).where(LedgerEntry.account_id == account_id)
        entries_res = await self.session.execute(entries_stmt)
        entries = entries_res.scalars().all()

        balance = 0
        for e in entries:
            if acc.normal_balance == NormalBalance.DEBIT.value:
                delta = e.amount_minor if e.direction == "DEBIT" else -e.amount_minor
            else:
                delta = e.amount_minor if e.direction == "CREDIT" else -e.amount_minor
            balance += delta

        return balance
