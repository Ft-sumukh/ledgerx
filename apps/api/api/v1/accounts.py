"""
LEDGER-ORBIT: Account Endpoints
================================
Routes for managing chart of accounts and querying live balances.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.api.deps import get_db_session
from packages.database.repository import AccountRepository, LedgerRepository
from packages.database.schemas import (
    AccountBalanceResponse,
    AccountCreate,
    AccountResponse,
)
from packages.shared_types.money import Currency, Money

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_db_session),
) -> AccountResponse:
    repo = AccountRepository(session)
    existing = await repo.get_by_number(payload.account_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account with number '{payload.account_number}' already exists",
        )
    account = await repo.create(payload)
    return AccountResponse.model_validate(account)


@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> List[AccountResponse]:
    repo = AccountRepository(session)
    accounts = await repo.list_all(limit=limit, offset=offset)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AccountResponse:
    repo = AccountRepository(session)
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    return AccountResponse.model_validate(account)


@router.get("/{account_id}/balance", response_model=AccountBalanceResponse)
async def get_account_balance(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AccountBalanceResponse:
    account_repo = AccountRepository(session)
    ledger_repo = LedgerRepository(session)

    account = await account_repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )

    # Derive exact historical balance directly from all entry legs
    derived_balance = await ledger_repo.derive_account_balance(account_id)
    curr = Currency(account.currency)
    formatted = str(Money(amount_minor=derived_balance, currency=curr))

    return AccountBalanceResponse(
        account_id=account.id,
        account_number=account.account_number,
        currency=account.currency,
        normal_balance=account.normal_balance,
        current_balance_minor=derived_balance,
        formatted_balance=formatted,
    )
