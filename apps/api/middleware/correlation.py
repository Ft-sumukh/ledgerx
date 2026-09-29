"""
LEDGER-ORBIT: Correlation ID Middleware
=========================================
Propagates X-Correlation-ID across every request.

DESIGN:
  Every HTTP request receives a unique correlation_id. If the caller supplies
  X-Correlation-ID, that value is used (enabling tracing across service calls).
  Otherwise a new UUID is generated. The ID is:
    - Stored in contextvars (available to all log calls in the request scope)
    - Echoed back in the response header X-Correlation-ID
    - Included in every log line emitted during the request

  This allows a single payment to be traced across:
    API request → Payment Intent → Ledger Transaction → Outbox Event
    → Queue Message → Worker → Webhook → Settlement → Audit Event
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from packages.logging.logger import bind_correlation_id, bind_request_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Extracts or generates X-Correlation-ID and X-Request-ID for every request.
    Both are bound into contextvars so they appear in all log lines automatically.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        bind_correlation_id(correlation_id)
        bind_request_id(request_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = request_id
        return response
