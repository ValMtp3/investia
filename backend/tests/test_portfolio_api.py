"""Tests des routes API portefeuille (service fake, zéro base)."""

import httpx
import pytest

from investia.main import create_app
from investia.portfolio import InsufficientFunds


class FakePortfolioService:
    def __init__(self):
        self.orders = []
        self.adjustments = []

    async def ensure_default_portfolio(self):
        return "p1"

    async def get_portfolio(self):
        return {
            "cash": 9_000.0,
            "positions": [],
            "positions_value": 0.0,
            "total_value": 9_000.0,
            "currency": "EUR",
            "initial_capital": 10_000.0,
        }

    async def place_order(self, symbol, side, quantity):
        if quantity > 100:
            raise InsufficientFunds("cash insuffisant")
        order = {"symbol": symbol, "side": side, "quantity": quantity, "fee": 1.0}
        self.orders.append(order)
        return order

    async def adjust_capital(self, amount, reason):
        self.adjustments.append((amount, reason))
        return {"cash": 9_000.0 + amount, "adjustment": amount, "reason": reason}

    async def list_orders(self, limit=50):
        return [
            {
                "id": f"order-{i}",
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": order["quantity"],
                "price": 100.0,
                "fee": order["fee"],
                "status": "simulated",
                "created_at": "2026-11-07T10:00:00+00:00",
            }
            for i, order in enumerate(self.orders)
        ][:limit]

    async def list_adjustments(self, limit=50):
        return [
            {
                "id": f"adj-{i}",
                "amount": amount,
                "reason": reason,
                "created_at": "2026-11-07T10:00:00+00:00",
            }
            for i, (amount, reason) in enumerate(self.adjustments)
        ][:limit]


ADMIN_SECRET = "test-admin-secret-0123456789abcdef"


@pytest.fixture
def client(monkeypatch):
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
    ):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", ADMIN_SECRET)
    app = create_app(portfolio_service=FakePortfolioService())
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_get_portfolio(client):
    response = await client.get("/portfolio")
    assert response.status_code == 200
    assert response.json()["currency"] == "EUR"


async def test_get_portfolio_exposes_initial_capital(client):
    """Le dashboard calcule la performance depuis le capital de départ (étape 7)."""
    response = await client.get("/portfolio")
    assert response.status_code == 200
    assert response.json()["initial_capital"] == 10_000.0


async def test_get_orders_empty_by_default(client):
    response = await client.get("/orders")
    assert response.status_code == 200
    assert response.json() == {"orders": []}


async def test_get_orders_returns_history_after_place(client):
    await client.post("/orders", json={"symbol": "AAPL", "side": "buy", "quantity": 2})
    await client.post(
        "/orders", json={"symbol": "BTC-USD", "side": "sell", "quantity": 0.5}
    )
    response = await client.get("/orders")
    assert response.status_code == 200
    orders = response.json()["orders"]
    assert len(orders) == 2
    for order in orders:
        assert set(order) == {
            "id",
            "symbol",
            "side",
            "quantity",
            "price",
            "fee",
            "status",
            "created_at",
        }
    assert {order["symbol"] for order in orders} == {"AAPL", "BTC-USD"}


async def test_get_orders_limit_is_validated(client):
    for bad_limit in (0, 201):
        response = await client.get("/orders", params={"limit": bad_limit})
        assert response.status_code == 422, bad_limit


async def test_get_portfolio_adjustments_history(client):
    response = await client.get("/portfolio/adjustments")
    assert response.status_code == 200
    assert response.json() == {"adjustments": []}
    response = await client.post(
        "/portfolio/adjust",
        json={"amount": 500, "reason": "test admin"},
        headers={"X-Admin-Token": ADMIN_SECRET},
    )
    assert response.status_code == 200
    response = await client.get("/portfolio/adjustments")
    adjustments = response.json()["adjustments"]
    assert len(adjustments) == 1
    assert adjustments[0]["amount"] == 500
    assert adjustments[0]["reason"] == "test admin"
    assert "created_at" in adjustments[0]


async def test_place_order_ok(client):
    response = await client.post(
        "/orders", json={"symbol": "AAPL", "side": "buy", "quantity": 2}
    )
    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"


async def test_place_order_insufficient_funds_is_400(client):
    response = await client.post(
        "/orders", json={"symbol": "AAPL", "side": "buy", "quantity": 500}
    )
    assert response.status_code == 400
    assert "insuffisant" in response.json()["detail"].lower()


async def test_adjust_requires_admin_token(client):
    response = await client.post(
        "/portfolio/adjust", json={"amount": 500, "reason": "test"}
    )
    assert response.status_code == 401
    response = await client.post(
        "/portfolio/adjust",
        json={"amount": 500, "reason": "test"},
        headers={"X-Admin-Token": ADMIN_SECRET},
    )
    assert response.status_code == 200
    assert response.json()["cash"] == 9_500.0


async def test_adjust_rejects_empty_and_non_ascii_tokens(client):
    """Jeton vide ou non ASCII : refus propre (401), jamais une erreur 500."""
    for bad_token in (b"", "é".encode()):
        response = await client.post(
            "/portfolio/adjust",
            json={"amount": 500, "reason": "test"},
            headers={"X-Admin-Token": bad_token},
        )
        assert response.status_code == 401, bad_token
