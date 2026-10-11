"""
LEDGER-ORBIT: API Dependencies
===============================
FastAPI dependencies for async database sessions and services.
"""

from __future__ import annotations

from typing import AsyncGenerator
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from packages.database.session import get_db_manager


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session per request."""
    db_manager = getattr(request.app.state, "db_manager", None)
    if db_manager is None:
        db_manager = get_db_manager()
    async with db_manager.session() as session:
        yield session
