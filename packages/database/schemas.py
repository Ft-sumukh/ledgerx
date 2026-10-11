"""
LEDGER-ORBIT: Pydantic Domain Schemas
=====================================
Validation and serialization schemas for Customer, Merchant, Account, Ledger, and Financial Reporting.

DESIGN:
  - Zero floats: monetary amounts represented strictly as int (minor units).
  - Strict validation of currency codes (ISO-4217).
  - from_attributes=True enables ORM model serialization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.shared_types.money import (
    AccountCategory,
    AccountType,
    Currency,
    EntryDirection,
    NormalBalance,
    PaymentStatus,
)


class CustomerCreate(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    metadata: Optional[dict[str, Any]] = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    email: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class MerchantCreate(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=100)
    business_name: str = Field(..., min_length=1, max_length=255)
    settlement_currency: Currency = Currency.USD
    metadata: Optional[dict[str, Any]] = None


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    business_name: str
    settlement_currency: str
    status: str
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    account_number: str = Field(..., min_length=1, max_length=64)
    account_type: AccountType
    category: Optional[AccountCategory] = None
    currency: Currency
    parent_account_id: Optional[str] = None
    owner_type: str = Field(..., pattern="^(CUSTOMER|MERCHANT|PLATFORM)$")
    owner_id: Optional[str] = None
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_number: str
    category: str
    account_type: str
    normal_balance: str
    currency: str
    parent_account_id: Optional[str] = None
    owner_type: str
    owner_id: Optional[str] = None
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None
    status: str
    current_balance_minor: int
    created_at: datetime
    updated_at: datetime


class AccountBalanceResponse(BaseModel):
    account_id: str
    account_number: str
    currency: str
    normal_balance: str
    current_balance_minor: int
    formatted_balance: str


class LedgerEntryInput(BaseModel):
    account_id: str = Field(..., min_length=1)
    direction: EntryDirection
    amount_minor: int = Field(..., gt=0)
    currency: Currency

    @field_validator("amount_minor")
    @classmethod
    def validate_amount_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Entry amount_minor must be strictly positive (> 0)")
        return v


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    transaction_id: str
    account_id: str
    direction: str
    amount_minor: int
    currency: str
    sequence: int
    created_at: datetime


class LedgerTransactionCreate(BaseModel):
    reference: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    currency: Currency
    entries: List[LedgerEntryInput] = Field(..., min_length=2)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("entries")
    @classmethod
    def validate_balance_invariant(cls, entries: List[LedgerEntryInput]) -> List[LedgerEntryInput]:
        debits = sum(e.amount_minor for e in entries if e.direction == EntryDirection.DEBIT)
        credits = sum(e.amount_minor for e in entries if e.direction == EntryDirection.CREDIT)
        if debits != credits:
            raise ValueError(
                f"Ledger transaction unbalanced! Debits ({debits}) != Credits ({credits}). Discrepancy: {debits - credits}"
            )
        return entries


class LedgerTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    status: str
    description: str
    currency: str
    posted_at: datetime
    correlation_id: str
    causation_id: Optional[str] = None
    related_transaction_id: Optional[str] = None
    entries: List[LedgerEntryResponse]
    created_at: datetime


class ReversalRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    reference: Optional[str] = None


class PaymentIntentCreate(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    amount_minor: int = Field(..., gt=0)
    currency: Currency
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class PaymentIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idempotency_key: str
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None
    amount_minor: int
    currency: str
    status: str
    client_secret: str
    description: Optional[str] = None
    correlation_id: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Reporting & Statements Models
# ---------------------------------------------------------------------------

class TrialBalanceItem(BaseModel):
    account_id: str
    account_number: str
    account_name: Optional[str] = None
    category: str
    account_type: str
    currency: str
    normal_balance: str
    total_debit_minor: int
    total_credit_minor: int
    net_balance_minor: int


class TrialBalanceReport(BaseModel):
    as_of: datetime
    currency: str
    accounts: List[TrialBalanceItem]
    total_debits_minor: int
    total_credits_minor: int
    is_balanced: bool
    discrepancy_minor: int


class CategorySummary(BaseModel):
    category: str
    total_minor: int
    accounts: List[TrialBalanceItem]


class BalanceSheetReport(BaseModel):
    as_of: datetime
    currency: str
    assets: CategorySummary
    liabilities: CategorySummary
    equity: CategorySummary
    total_assets_minor: int
    total_liabilities_and_equity_minor: int
    is_balanced: bool
    variance_minor: int


class IncomeStatementReport(BaseModel):
    from_date: Optional[datetime] = None
    to_date: datetime
    currency: str
    revenue: CategorySummary
    expenses: CategorySummary
    total_revenue_minor: int
    total_expenses_minor: int
    net_income_minor: int


class AccountStatementEntry(BaseModel):
    entry_id: str
    transaction_id: str
    transaction_reference: str
    posted_at: datetime
    description: str
    direction: str
    amount_minor: int
    running_balance_minor: int


class AccountStatementReport(BaseModel):
    account_id: str
    account_number: str
    account_type: str
    category: str
    currency: str
    normal_balance: str
    opening_balance_minor: int
    closing_balance_minor: int
    entries: List[AccountStatementEntry]
