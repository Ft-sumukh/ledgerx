"""
LEDGER-ORBIT: Merchant Endpoints
=================================
Routes for managing business merchants.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.api.deps import get_db_session
from packages.database.repository import MerchantRepository
from packages.database.schemas import MerchantCreate, MerchantResponse

router = APIRouter(prefix="/merchants", tags=["Merchants"])


@router.post("", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def create_merchant(
    payload: MerchantCreate,
    session: AsyncSession = Depends(get_db_session),
) -> MerchantResponse:
    repo = MerchantRepository(session)
    merchant = await repo.create(payload)
    return MerchantResponse.model_validate(merchant)


@router.get("", response_model=List[MerchantResponse])
async def list_merchants(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> List[MerchantResponse]:
    repo = MerchantRepository(session)
    merchants = await repo.list_all(limit=limit, offset=offset)
    return [MerchantResponse.model_validate(m) for m in merchants]


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> MerchantResponse:
    repo = MerchantRepository(session)
    merchant = await repo.get_by_id(merchant_id)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant '{merchant_id}' not found",
        )
    return MerchantResponse.model_validate(merchant)
