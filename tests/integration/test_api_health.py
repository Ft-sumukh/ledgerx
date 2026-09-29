"""
Integration tests for the API health endpoint.

These tests start the actual FastAPI application (with SQLite in-memory DB)
and verify the health endpoint returns correct responses with proper headers.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/health")
        assert response.status_code == 200

    async def test_health_response_has_status_field(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")

    async def test_health_includes_components(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/health")
        data = response.json()
        assert "components" in data
        assert "database" in data["components"]
        assert "queue" in data["components"]

    async def test_health_includes_uptime(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/health")
        data = response.json()
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    async def test_health_includes_version(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/health")
        data = response.json()
        assert data["version"] == "0.1.0"

    async def test_correlation_id_in_response_headers(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/health")
        assert "x-correlation-id" in response.headers
        assert "x-request-id" in response.headers

    async def test_custom_correlation_id_echoed(self, client: AsyncClient) -> None:
        custom_id = "test-correlation-12345"
        response = await client.get(
            "/api/v1/system/health",
            headers={"X-Correlation-ID": custom_id},
        )
        assert response.headers["x-correlation-id"] == custom_id

    async def test_metrics_endpoint_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/metrics")
        assert response.status_code == 200

    async def test_metrics_has_required_fields(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/metrics")
        data = response.json()
        assert "uptime_seconds" in data
        assert "python_version" in data
        assert "pid" in data
        assert "environment" in data

    async def test_openapi_docs_available(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        assert "openapi" in response.json()
