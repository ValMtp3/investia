"""Tests d'intégration du portefeuille : vraie base (conteneur pgvector, 5432)."""

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from investia.db import get_session
from investia.market.base import MarketData
from investia.portfolio import InsufficientFunds, PortfolioService

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]


class FakeMarket:
    async def get_quote(self, symbol):
        if symbol == "USD":
            return MarketData(
                value=0.895,
                currency="EUR",
                source="frankfurter",
                timestamp=datetime(2026, 10, 31, tzinfo=UTC),
            )
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


@pytest.fixture
async def service(monkeypatch):
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    import investia.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    # base persistante entre les runs : on nettoie les tables portefeuille
    async with get_session()() as session:
        await session.execute(
            text("TRUNCATE orders, positions, capital_adjustments, portfolios CASCADE")
        )
        await session.commit()
    yield PortfolioService(get_session(), FakeMarket())
    db_module._engine = None
    db_module._session_factory = None


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
def test_alembic_upgrade_head_creates_portfolio_tables():
    assert TEST_DATABASE_URL is not None
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
async def test_full_order_scenario_on_real_db(service):
    # prix AAPL en EUR = 344.63 * 0.895 = 308.34...
    price_eur = 344.63 * 0.895
    order = await service.place_order("AAPL", "buy", 10)
    fee = round(10 * price_eur * 0.001, 2)
    assert order["fee"] == pytest.approx(fee)
    assert order["cash_after"] == pytest.approx(10_000 - 10 * price_eur - fee)

    portfolio = await service.get_portfolio()
    assert portfolio["cash"] == pytest.approx(order["cash_after"])
    assert portfolio["positions"][0]["symbol"] == "AAPL"
    assert portfolio["positions"][0]["quantity"] == 10.0
    # après un achat, la valeur totale = capital - frais (les frais sont dépensés)
    assert portfolio["total_value"] == pytest.approx(10_000.0 - fee, abs=0.01)

    # vente partielle
    sell = await service.place_order("AAPL", "sell", 4)
    portfolio2 = await service.get_portfolio()
    assert portfolio2["positions"][0]["quantity"] == pytest.approx(6.0)
    assert sell["cash_after"] > order["cash_after"]

    # achat au-delà du cash -> erreur, rien d'écrit
    with pytest.raises(InsufficientFunds):
        await service.place_order("AAPL", "buy", 10_000)

    # ajustement admin
    adj = await service.adjust_capital(500.0, "test admin")
    assert adj["cash"] == pytest.approx(portfolio2["cash"] + 500.0)
