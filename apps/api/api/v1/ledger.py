"""
LEDGER-ORBIT: Ledger Transaction Endpoints
===========================================
Routes for atomic posting of balanced multi-legged double-entry transactions
and querying the immutable general ledger journal.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.api.deps import get_db_session
from packages.database.repository import (
    AccountCurrencyMismatchError,
    EntityNotFoundError,
    LedgerRepository,
    LedgerUnbalancedError,
)
from packages.database.schemas import (
    LedgerTransactionCreate,
    LedgerTransactionResponse,
)

router = APIRouter(prefix="/ledger", tags=["Ledger"])


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
