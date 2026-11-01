"""Tests de GET /market/history : clôtures pour le graphique (spec 4.4c)."""

from datetime import UTC, datetime

import httpx
import pytest

from investia.main import create_app
from investia.market.base import MarketData, MarketDataError


def close(day: int, value: float, hour: int = 0, **kwargs) -> MarketData:
    return MarketData(
        value=value,
        currency=kwargs.pop("currency", "USD"),
        source=kwargs.pop("source", "yahoo"),
        timestamp=datetime(2026, 10, day, hour, tzinfo=UTC),
        delayed=kwargs.pop("delayed", False),
    )


class FakeMarket:
    """Faux service de marché : renvoie l'historique donné, ou lève l'erreur donnée."""

    def __init__(self, history=None, error=None):
        self._history = history or []
        self._error = error
        self.calls: list[tuple[str, int]] = []

    async def get_history(self, symbol, days=30):
        self.calls.append((symbol, days))
        if self._error:
            raise self._error
        return self._history

    async def get_quote(self, symbol):
        raise NotImplementedError

    async def get_news(self, symbol, limit=5):
        return []


class FakePortfolio:
    async def get_portfolio(self):
        return {}


def make_client(market: FakeMarket, monkeypatch) -> httpx.AsyncClient:
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "APP_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "x")
    app = create_app(portfolio_service=FakePortfolio(), llm=object(), market=market)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_history_returns_sorted_points_with_source_and_currency(monkeypatch):
    market = FakeMarket([close(3, 103.5), close(1, 101.0), close(2, 102.25)])
    async with make_client(market, monkeypatch) as client:
        response = await client.get("/market/history", params={"symbol": "aapl"})
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AAPL"
    assert body["source"] == "yahoo"
    assert body["currency"] == "USD"
    assert body["points"] == [
        {"time": "2026-10-01", "value": 101.0},
        {"time": "2026-10-02", "value": 102.25},
        {"time": "2026-10-03", "value": 103.5},
    ]
    # symbole mis en majuscules, 30 jours par défaut
    assert market.calls == [("AAPL", 30)]


async def test_history_keeps_one_point_per_day_last_one_wins(monkeypatch):
    # lightweight-charts plante si deux points ont la même date
    market = FakeMarket(
        [close(1, 100.0, hour=9), close(1, 100.8, hour=17), close(2, 101.0)]
    )
    async with make_client(market, monkeypatch) as client:
        response = await client.get("/market/history", params={"symbol": "AAPL"})
    points = response.json()["points"]
    assert [p["time"] for p in points] == ["2026-10-01", "2026-10-02"]
    assert points[0]["value"] == 100.8


async def test_history_flags_delayed_when_a_point_is_delayed(monkeypatch):
    market = FakeMarket([close(1, 1.0), close(2, 2.0, delayed=True)])
    async with make_client(market, monkeypatch) as client:
        response = await client.get("/market/history", params={"symbol": "AAPL"})
    assert response.json()["delayed"] is True


async def test_history_empty_is_a_valid_answer(monkeypatch):
    async with make_client(FakeMarket([]), monkeypatch) as client:
        response = await client.get("/market/history", params={"symbol": "AAPL"})
    assert response.status_code == 200
    body = response.json()
    assert body["points"] == []
    assert body["source"] is None
    assert body["currency"] is None
    assert body["delayed"] is False


async def test_history_passes_days_to_the_market_service(monkeypatch):
    market = FakeMarket([close(1, 1.0)])
    async with make_client(market, monkeypatch) as client:
        await client.get("/market/history", params={"symbol": "BTC-USD", "days": 90})
    assert market.calls == [("BTC-USD", 90)]


@pytest.mark.parametrize("symbol", ["", "AA PL", "<script>", "A" * 21, "AAPL;DROP"])
async def test_history_rejects_invalid_symbol(monkeypatch, symbol):
    market = FakeMarket([close(1, 1.0)])
    async with make_client(market, monkeypatch) as client:
        response = await client.get("/market/history", params={"symbol": symbol})
    assert response.status_code == 422
    assert market.calls == []


@pytest.mark.parametrize("days", [4, 401, 0, -3])
async def test_history_rejects_days_out_of_bounds(monkeypatch, days):
    market = FakeMarket([close(1, 1.0)])
    async with make_client(market, monkeypatch) as client:
        response = await client.get(
            "/market/history", params={"symbol": "AAPL", "days": days}
        )
    assert response.status_code == 422
    assert market.calls == []


async def test_history_provider_error_is_a_clear_502_naming_the_source(monkeypatch):
    market = FakeMarket(error=MarketDataError("eodhd", "clé API manquante"))
    async with make_client(market, monkeypatch) as client:
        response = await client.get("/market/history", params={"symbol": "SAP.DE"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "eodhd" in detail
    assert "clé API manquante" in detail
