"""
LEDGER-ORBIT: Customer Endpoints
=================================
Routes for managing customers in the financial ecosystem.
"""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.api.deps import get_db_session
from packages.database.repository import CustomerRepository
from packages.database.schemas import CustomerCreate, CustomerResponse

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    session: AsyncSession = Depends(get_db_session),
) -> CustomerResponse:
    repo = CustomerRepository(session)
    existing = await repo.get_by_external_id(payload.external_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Customer with external_id '{payload.external_id}' already exists",
        )
    customer = await repo.create(payload)
    return CustomerResponse.model_validate(customer)


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> List[CustomerResponse]:
    repo = CustomerRepository(session)
    customers = await repo.list_all(limit=limit, offset=offset)
    return [CustomerResponse.model_validate(c) for c in customers]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> CustomerResponse:
    repo = CustomerRepository(session)
    customer = await repo.get_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{customer_id}' not found",
        )
    return CustomerResponse.model_validate(customer)
