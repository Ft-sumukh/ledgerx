"""
LEDGER-ORBIT: FastAPI Application Entry Point
==============================================
Defines the FastAPI app with:
  - Application lifespan (startup + shutdown)
  - Middleware stack (CORS, Correlation IDs, Request Logging)
  - Versioned API router registration
  - OpenAPI metadata

DESIGN:
  The lifespan context manager initializes expensive resources once at startup
  (database engine, queue) and disposes them cleanly at shutdown. This is the
  recommended FastAPI pattern over deprecated on_event handlers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.api.v1.router import api_router
from apps.api.middleware.correlation import CorrelationIdMiddleware
from apps.api.middleware.logging import RequestLoggingMiddleware
from packages.configuration.settings import get_settings
from packages.database.session import DatabaseManager, set_db_manager
from packages.logging.logger import OrbitLogger, get_logger
from packages.queue.memory import InMemoryQueue

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    # 1. Configure structured logging
    OrbitLogger.configure(level=settings.log_level, fmt=settings.log_format)
    logger.info(
        "LEDGER-ORBIT starting",
        extra={
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )

    # 2. Initialize database
    db_manager = DatabaseManager(
        database_url=settings.database_url,
        echo=settings.database_echo,
    )
    await db_manager.initialize(create_tables=True)
    set_db_manager(db_manager)
    app.state.db_manager = db_manager

    # 3. Initialize in-memory queue (broker-agnostic abstraction)
    queue = InMemoryQueue(max_receive_count=settings.queue_max_receive_count)
    app.state.queue = queue
    logger.info("Queue initialized", extra={"implementation": "InMemoryQueue"})

    logger.info("LEDGER-ORBIT startup complete — ready to accept requests")
    yield

    # Shutdown
    logger.info("LEDGER-ORBIT shutting down")
    await db_manager.dispose()
    logger.info("LEDGER-ORBIT shutdown complete")


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title="LEDGER-ORBIT",
        description=(
            "Distributed Financial Ledger & Cloud Computing Platform — "
            "a production-style engineering platform demonstrating payment processing, "
            "double-entry accounting, distributed job processing, event-driven architecture, "
            "and reliability engineering.\n\n"
            "⚠️ Research/Educational Platform — No real money."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS — allow Next.js frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation IDs (must be added after CORS)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # Register versioned API routes
    app.include_router(api_router)

    return app


# The ASGI app instance used by uvicorn
app = create_app()
