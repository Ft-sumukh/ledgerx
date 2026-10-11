"""
Integration tests for Customer, Merchant, Account, and Ledger API v1 routes.
Verifies end-to-end HTTP request processing, double-entry validation, and error mapping.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


from packages.database.base import Base
from packages.database.session import get_db_manager


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        db_manager = get_db_manager()
        async with db_manager.session() as s:
            for table in reversed(Base.metadata.sorted_tables):
                await s.execute(table.delete())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
class TestDomainAPIRoutes:
    async def test_create_and_get_customer(self, client: AsyncClient) -> None:
        payload = {
            "external_id": "cust_api_100",
            "email": "cust_api@example.com",
            "name": "Sarah Connor",
        }
        res = await client.post("/api/v1/customers", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["external_id"] == "cust_api_100"
        assert data["email"] == "cust_api@example.com"
        assert "id" in data

        cust_id = data["id"]
        get_res = await client.get(f"/api/v1/customers/{cust_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Sarah Connor"

    async def test_duplicate_customer_rejected(self, client: AsyncClient) -> None:
        payload = {
            "external_id": "cust_duplicate_test",
            "email": "dup@example.com",
            "name": "Duplicate User",
        }
        res1 = await client.post("/api/v1/customers", json=payload)
        assert res1.status_code == 201

        res2 = await client.post("/api/v1/customers", json=payload)
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]

    async def test_create_and_list_merchants(self, client: AsyncClient) -> None:
        payload = {
            "external_id": "merch_api_01",
            "business_name": "Cyberdyne Systems",
            "settlement_currency": "USD",
        }
        res = await client.post("/api/v1/merchants", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["business_name"] == "Cyberdyne Systems"
        assert data["settlement_currency"] == "USD"

        list_res = await client.get("/api/v1/merchants")
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

    async def test_create_account_and_post_balanced_transaction(self, client: AsyncClient) -> None:
        # 1. Create Customer and Merchant accounts
        acc1_res = await client.post(
            "/api/v1/accounts",
            json={
                "account_number": "1010-SARAH-USD",
                "account_type": "CUSTOMER",
                "currency": "USD",
                "owner_type": "CUSTOMER",
            },
        )
        assert acc1_res.status_code == 201
        acc_cust = acc1_res.json()

        acc2_res = await client.post(
            "/api/v1/accounts",
            json={
                "account_number": "2010-CYBERDYNE-USD",
                "account_type": "MERCHANT",
                "currency": "USD",
                "owner_type": "MERCHANT",
            },
        )
        assert acc2_res.status_code == 201
        acc_merch = acc2_res.json()

        # 2. Post balanced transaction: $25.00 (2500 cents)
        tx_payload = {
            "reference": "tx_api_balanced_01",
            "description": "Payment for software license",
            "currency": "USD",
            "entries": [
                {
                    "account_id": acc_cust["id"],
                    "direction": "CREDIT",
                    "amount_minor": 2500,
                    "currency": "USD",
                },
                {
                    "account_id": acc_merch["id"],
                    "direction": "DEBIT",
                    "amount_minor": 2500,
                    "currency": "USD",
                },
            ],
        }
        tx_res = await client.post("/api/v1/ledger/transactions", json=tx_payload)
        assert tx_res.status_code == 201, tx_res.text
        tx_data = tx_res.json()
        assert tx_data["reference"] == "tx_api_balanced_01"
        assert len(tx_data["entries"]) == 2

        # 3. Query account live balance
        bal_res = await client.get(f"/api/v1/accounts/{acc_cust['id']}/balance")
        assert bal_res.status_code == 200
        bal_data = bal_res.json()
        assert bal_data["current_balance_minor"] == -2500
        assert bal_data["formatted_balance"] == "$-25.00"

    async def test_unbalanced_transaction_rejected_by_api(self, client: AsyncClient) -> None:
        # Schema validator catches unbalanced input and returns 422
        tx_payload = {
            "reference": "tx_unbalanced_api",
            "description": "Unbalanced payment",
            "currency": "USD",
            "entries": [
                {
                    "account_id": "dummy_acc_1",
                    "direction": "CREDIT",
                    "amount_minor": 1000,
                    "currency": "USD",
                },
                {
                    "account_id": "dummy_acc_2",
                    "direction": "DEBIT",
                    "amount_minor": 900,  # missing 100
                    "currency": "USD",
                },
            ],
        }
        res = await client.post("/api/v1/ledger/transactions", json=tx_payload)
        assert res.status_code == 422
        assert "unbalanced" in res.text.lower()
