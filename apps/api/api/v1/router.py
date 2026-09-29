"""
LEDGER-ORBIT: API v1 Router
============================
Aggregates all v1 route modules into a single router.
"""

from fastapi import APIRouter

from apps.api.api.v1 import health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
