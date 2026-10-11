"""
LEDGER-ORBIT: Ledger Transaction & Reporting Endpoints
======================================================
Routes for atomic posting of balanced multi-legged double-entry transactions,
immutable compensating reversals, and GAAP/IFRS financial statements:
  - Trial Balance
  - Balance Sheet
  - Income Statement
  - Account General Ledger Statements
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.api.deps import get_db_session
from packages.database.repository import (
    AccountCurrencyMismatchError,
    EntityNotFoundError,
    LedgerRepository,
    LedgerUnbalancedError,
)
from packages.database.schemas import (
    AccountResponse,
    AccountStatementReport,
    BalanceSheetReport,
    IncomeStatementReport,
    LedgerTransactionCreate,
    LedgerTransactionResponse,
    ReversalRequest,
    TrialBalanceReport,
)
from packages.shared_types.money import Currency
from services.ledger.reports import FinancialReportingService
from services.ledger.service import (
    LedgerService,
    TransactionAlreadyReversedError,
    TransactionNotReversibleError,
)

router = APIRouter(prefix="/ledger", tags=["Ledger"])


# ---------------------------------------------------------------------------
# Journal Transactions & Reversals
# ---------------------------------------------------------------------------

@router.post("/transactions", response_model=LedgerTransactionResponse, status_code=status.HTTP_201_CREATED)
async def post_transaction(
    payload: LedgerTransactionCreate,
    x_correlation_id: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> LedgerTransactionResponse:
    repo = LedgerRepository(session)
    correlation_id = x_correlation_id or payload.correlation_id or "corr_direct"

    existing = await repo.get_by_reference(payload.reference)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transaction with reference '{payload.reference}' already exists",
        )

    try:
        tx = await repo.post_transaction(payload, correlation_id=correlation_id)
        return LedgerTransactionResponse.model_validate(tx)
    except LedgerUnbalancedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except (EntityNotFoundError, AccountCurrencyMismatchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/transactions", response_model=List[LedgerTransactionResponse])
async def list_transactions(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> List[LedgerTransactionResponse]:
    repo = LedgerRepository(session)
    transactions = await repo.list_transactions(limit=limit, offset=offset)
    return [LedgerTransactionResponse.model_validate(t) for t in transactions]


@router.get("/transactions/{reference}", response_model=LedgerTransactionResponse)
async def get_transaction(
    reference: str,
    session: AsyncSession = Depends(get_db_session),
) -> LedgerTransactionResponse:
    repo = LedgerRepository(session)
    tx = await repo.get_by_reference(reference)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with reference '{reference}' not found",
        )
    return LedgerTransactionResponse.model_validate(tx)


@router.post("/reversals/{reference}", response_model=LedgerTransactionResponse, status_code=status.HTTP_201_CREATED)
async def reverse_transaction(
    reference: str,
    payload: ReversalRequest,
    x_correlation_id: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> LedgerTransactionResponse:
    service = LedgerService(session)
    correlation_id = x_correlation_id or "corr_reversal"

    try:
        rev_tx = await service.create_compensating_reversal(
            original_reference=reference,
            reason=payload.reason,
            correlation_id=correlation_id,
            reversal_reference=payload.reference,
        )
        return LedgerTransactionResponse.model_validate(rev_tx)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (TransactionAlreadyReversedError, TransactionNotReversibleError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Financial Reporting Endpoints
# ---------------------------------------------------------------------------

@router.get("/reports/trial-balance", response_model=TrialBalanceReport)
async def get_trial_balance(
    as_of: Optional[datetime] = None,
    currency: Optional[Currency] = None,
    session: AsyncSession = Depends(get_db_session),
) -> TrialBalanceReport:
    reporting = FinancialReportingService(session)
    return await reporting.generate_trial_balance(as_of=as_of, currency=currency)


@router.get("/reports/balance-sheet", response_model=BalanceSheetReport)
async def get_balance_sheet(
    as_of: Optional[datetime] = None,
    currency: Optional[Currency] = None,
    session: AsyncSession = Depends(get_db_session),
) -> BalanceSheetReport:
    reporting = FinancialReportingService(session)
    return await reporting.generate_balance_sheet(as_of=as_of, currency=currency)


@router.get("/reports/income-statement", response_model=IncomeStatementReport)
async def get_income_statement(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    currency: Optional[Currency] = None,
    session: AsyncSession = Depends(get_db_session),
) -> IncomeStatementReport:
    reporting = FinancialReportingService(session)
    return await reporting.generate_income_statement(from_date=from_date, to_date=to_date, currency=currency)


@router.get("/accounts/{account_id}/statement", response_model=AccountStatementReport)
async def get_account_statement(
    account_id: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_db_session),
) -> AccountStatementReport:
    reporting = FinancialReportingService(session)
    try:
        return await reporting.generate_account_statement(
            account_id=account_id,
            from_date=from_date,
            to_date=to_date,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/chart-of-accounts/seed", response_model=List[AccountResponse], status_code=status.HTTP_201_CREATED)
async def seed_chart_of_accounts(
    tenant_id: str = Query(..., min_length=1, max_length=50),
    currency: Currency = Query(Currency.USD),
    session: AsyncSession = Depends(get_db_session),
) -> List[AccountResponse]:
    service = LedgerService(session)
    accounts = await service.seed_default_chart_of_accounts(tenant_id=tenant_id, currency=currency)
    return [AccountResponse.model_validate(a) for a in accounts]
