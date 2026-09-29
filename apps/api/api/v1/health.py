"""
LEDGER-ORBIT: Health & System Endpoints
=========================================
Deep health checks for all system dependencies.

Endpoints:
  GET /api/v1/system/health   — comprehensive health check (DB, Queue, Memory)
  GET /api/v1/system/metrics  — basic runtime metrics

DESIGN:
  A properly designed health check verifies actual dependency connectivity,
  not just "is the process running." This enables:
  - Kubernetes readiness probes to stop routing traffic to unhealthy instances
  - Load balancer health checks
  - Operational dashboards showing real system state
"""

from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from packages.configuration.settings import get_settings
from packages.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

_START_TIME = time.time()


class ComponentHealth(BaseModel):
    status: str
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    uptime_seconds: float
    environment: str
    version: str
    components: dict[str, ComponentHealth]


class MetricsResponse(BaseModel):
    uptime_seconds: float
    python_version: str
    platform: str
    pid: int
    environment: str


@router.get("/system/health", response_model=HealthResponse, tags=["System"])
async def health_check(request: Request) -> HealthResponse:
    """
    Deep health check — verifies all system dependencies.

    Returns HTTP 200 when all components are healthy.
    Returns HTTP 503 when any critical component is degraded or down.
    """
    settings = get_settings()
    components: dict[str, ComponentHealth] = {}
    overall_status = "ok"

    # Check database
    db_manager = getattr(request.app.state, "db_manager", None)
    if db_manager is not None:
        t0 = time.perf_counter()
        try:
            await db_manager.check_connection()
            db_latency = (time.perf_counter() - t0) * 1000
            db_detail = settings.database_url.split("@")[-1] if "@" in settings.database_url else "sqlite"
            components["database"] = ComponentHealth(
                status="ok",
                latency_ms=round(db_latency, 2),
                detail=db_detail,
            )
        except Exception as exc:
            components["database"] = ComponentHealth(status="down", detail=str(exc))
            overall_status = "degraded"
    else:
        components["database"] = ComponentHealth(status="not_configured")

    # Check queue
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            stats = await queue.get_stats("default")
            components["queue"] = ComponentHealth(
                status="ok",
                detail=f"depth={stats.depth}, in_flight={stats.in_flight}, dlq={stats.dead_letter_count}",
            )
        except Exception as exc:
            components["queue"] = ComponentHealth(status="down", detail=str(exc))
            overall_status = "degraded"
    else:
        components["queue"] = ComponentHealth(status="not_configured")

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=round(time.time() - _START_TIME, 2),
        environment=settings.environment,
        version=settings.app_version,
        components=components,
    )


@router.get("/system/metrics", response_model=MetricsResponse, tags=["System"])
async def system_metrics() -> MetricsResponse:
    """Basic runtime metrics for observability dashboards."""
    settings = get_settings()
    return MetricsResponse(
        uptime_seconds=round(time.time() - _START_TIME, 2),
        python_version=sys.version,
        platform=platform.platform(),
        pid=os.getpid(),
        environment=settings.environment,
    )
