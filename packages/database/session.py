"""
LEDGER-ORBIT: Database Session Manager
========================================
Provides async SQLAlchemy engine and session management.

DESIGN DECISIONS:
  - Uses SQLAlchemy 2.0 async API for non-blocking database I/O.
  - Supports PostgreSQL (production) and SQLite (development/test).
  - DatabaseManager is a singleton initialized once at application startup.
  - check_connection() verifies database reachability for health checks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from packages.database.base import Base
from packages.logging.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """
    Manages the SQLAlchemy async engine and session factory.

    Lifecycle:
        manager = DatabaseManager(url)
        await manager.initialize()
        async with manager.session() as session:
            ...
        await manager.dispose()
    """

    def __init__(self, database_url: str, echo: bool = False) -> None:
        self._url = database_url
        self._echo = echo
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self, create_tables: bool = True) -> None:
        """Create async engine, verify connectivity, optionally create tables."""
        connect_args: dict = {}
        if self._url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        self._engine = create_async_engine(
            self._url,
            echo=self._echo,
            connect_args=connect_args,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        if create_tables:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created/verified")

        await self.check_connection()

    async def check_connection(self) -> bool:
        """Verify database is reachable. Returns True on success."""
        if not self._engine:
            raise RuntimeError("DatabaseManager not initialized. Call initialize() first.")
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
        return True

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide an async database session with automatic commit/rollback."""
        if not self._session_factory:
            raise RuntimeError("DatabaseManager not initialized. Call initialize() first.")
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Dispose of the connection pool at application shutdown."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connection pool disposed")

    @property
    def engine(self) -> AsyncEngine:
        if not self._engine:
            raise RuntimeError("DatabaseManager not initialized.")
        return self._engine


_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Return the initialized DatabaseManager singleton."""
    if _db_manager is None:
        raise RuntimeError("Database manager not initialized. Call set_db_manager() first.")
    return _db_manager


def set_db_manager(manager: DatabaseManager) -> None:
    """Register the DatabaseManager singleton (called during app startup)."""
    global _db_manager
    _db_manager = manager
