"""
LEDGER-ORBIT: API v1 Router
============================
Aggregates all v1 route modules into a single router.
"""

from fastapi import APIRouter

from apps.api.api.v1 import accounts, customers, health, ledger, merchants

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(customers.router)
api_router.include_router(merchants.router)
api_router.include_router(accounts.router)
api_router.include_router(ledger.router)
