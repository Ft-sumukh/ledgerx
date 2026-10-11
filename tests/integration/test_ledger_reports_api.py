"""
Integration tests for Ledger Reversals, Financial Statements, and Chart of Accounts API routes.
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
class TestLedgerReportsAPI:
    async def test_seed_chart_of_accounts(self, client: AsyncClient) -> None:
        res = await client.post("/api/v1/ledger/chart-of-accounts/seed?tenant_id=org_acme&currency=USD")
        assert res.status_code == 201, res.text
        accounts = res.json()
        assert len(accounts) >= 10
        # Check standard account categories exist
        account_numbers = [a["account_number"] for a in accounts]
        assert any("1010-org_acme-USD" in num for num in account_numbers)
        assert any("2010-org_acme-USD" in num for num in account_numbers)
        assert any("3010-org_acme-USD" in num for num in account_numbers)

    async def test_post_and_reverse_transaction_via_api(self, client: AsyncClient) -> None:
        # 1. Create accounts
        acc1_res = await client.post(
            "/api/v1/accounts",
            json={
                "account_number": "1010-REV-USER",
                "account_type": "CUSTOMER",
                "currency": "USD",
                "owner_type": "CUSTOMER",
            },
        )
        assert acc1_res.status_code == 201
        acc1 = acc1_res.json()

        acc2_res = await client.post(
            "/api/v1/accounts",
            json={
                "account_number": "2010-REV-MERCH",
                "account_type": "MERCHANT",
                "currency": "USD",
                "owner_type": "MERCHANT",
            },
        )
        assert acc2_res.status_code == 201
        acc2 = acc2_res.json()

        # 2. Post transaction: $75.00 (7500 cents)
        tx_res = await client.post(
            "/api/v1/ledger/transactions",
            json={
                "reference": "tx_to_be_reversed",
                "description": "Subscription charge",
                "currency": "USD",
                "entries": [
                    {"account_id": acc1["id"], "direction": "CREDIT", "amount_minor": 7500, "currency": "USD"},
                    {"account_id": acc2["id"], "direction": "DEBIT", "amount_minor": 7500, "currency": "USD"},
                ],
            },
        )
        assert tx_res.status_code == 201

        # 3. Reverse the transaction
        rev_res = await client.post(
            "/api/v1/ledger/reversals/tx_to_be_reversed",
            json={"reason": "Customer cancellation within refund window"},
        )
        assert rev_res.status_code == 201, rev_res.text
        rev_data = rev_res.json()
        assert "rev_tx_to_be_reversed" in rev_data["reference"]
        assert len(rev_data["entries"]) == 2

        # 4. Check that balance returned to 0
        bal_res = await client.get(f"/api/v1/accounts/{acc1['id']}/balance")
        assert bal_res.status_code == 200
        assert bal_res.json()["current_balance_minor"] == 0

    async def test_financial_reports_endpoints(self, client: AsyncClient) -> None:
        # Trial Balance
        tb_res = await client.get("/api/v1/ledger/reports/trial-balance?currency=USD")
        assert tb_res.status_code == 200
        tb = tb_res.json()
        assert tb["is_balanced"] is True
        assert tb["discrepancy_minor"] == 0

        # Balance Sheet
        bs_res = await client.get("/api/v1/ledger/reports/balance-sheet?currency=USD")
        assert bs_res.status_code == 200
        bs = bs_res.json()
        assert "assets" in bs
        assert "liabilities" in bs
        assert "equity" in bs
        assert bs["variance_minor"] == 0

        # Income Statement
        inc_res = await client.get("/api/v1/ledger/reports/income-statement?currency=USD")
        assert inc_res.status_code == 200
        inc = inc_res.json()
        assert "revenue" in inc
        assert "expenses" in inc
        assert "net_income_minor" in inc

    async def test_account_statement_endpoint(self, client: AsyncClient) -> None:
        # Create an account and query statement
        acc_res = await client.post(
            "/api/v1/accounts",
            json={
                "account_number": "1010-STMT-TEST",
                "account_type": "CUSTOMER",
                "currency": "USD",
                "owner_type": "CUSTOMER",
            },
        )
        assert acc_res.status_code == 201
        acc = acc_res.json()

        stmt_res = await client.get(f"/api/v1/ledger/accounts/{acc['id']}/statement")
        assert stmt_res.status_code == 200
        stmt = stmt_res.json()
        assert stmt["account_number"] == "1010-STMT-TEST"
        assert "entries" in stmt
        assert stmt["opening_balance_minor"] == 0
        assert stmt["closing_balance_minor"] == 0
