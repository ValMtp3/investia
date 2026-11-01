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


@pytest.fixture
def client(monkeypatch):
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "APP_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", "admin-secret")
    app = create_app(portfolio_service=FakePortfolioService())
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_get_portfolio(client):
    response = await client.get("/portfolio")
    assert response.status_code == 200
    assert response.json()["currency"] == "EUR"


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
        headers={"X-Admin-Token": "admin-secret"},
    )
    assert response.status_code == 200
    assert response.json()["cash"] == 9_500.0
