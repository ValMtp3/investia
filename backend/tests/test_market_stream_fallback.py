"""Repli d'affichage : si le prix échoue, /market/stream envoie la dernière clôture.

Spec 4.4d. Seule la route d'affichage est concernée : `get_quote` (agent, portefeuille)
garde son erreur claire plutôt qu'un prix de la veille pris pour un prix du jour.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest

from investia.main import create_app
from investia.market.base import MarketData, MarketDataError


def close(day: int, value: float) -> MarketData:
    return MarketData(
        value=value,
        currency="EUR",
        source="eodhd",
        timestamp=datetime(2026, 10, day, tzinfo=UTC),
        delayed=True,
    )


class FakeMarket:
    def __init__(self, history_error: MarketDataError | None = None):
        self._history_error = history_error
        self.history_calls: list[tuple[str, int]] = []

    async def get_quote(self, symbol):
        if symbol == "SAP.DE":
            raise MarketDataError("yahoo", "HTTP 429 pour SAP.DE", rate_limited=True)
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 11, 1, 13, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        self.history_calls.append((symbol, days))
        if self._history_error:
            raise self._history_error
        return [close(29, 188.0), close(30, 189.4)]

    async def get_news(self, symbol, limit=5):
        return []


class FakePortfolio:
    async def get_portfolio(self):
        return {}


async def first_quotes(market: FakeMarket, monkeypatch) -> dict[str, dict]:
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "APP_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "x")
    app = create_app(portfolio_service=FakePortfolio(), llm=object(), market=market)
    transport = httpx.ASGITransport(app=app)
    url = "/market/stream?symbols=AAPL,SAP.DE&interval=0.05&max_events=1"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", url) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])
    data_line = next(line for line in body.splitlines() if line.startswith("data:"))
    quotes = json.loads(data_line[len("data:") :])["quotes"]
    return {quote["symbol"]: quote for quote in quotes}


async def test_failed_quote_falls_back_to_the_last_close_and_says_so(monkeypatch):
    quotes = await first_quotes(FakeMarket(), monkeypatch)
    sap = quotes["SAP.DE"]
    assert sap["value"] == 189.4
    assert sap["currency"] == "EUR"
    assert sap["source"] == "eodhd"
    assert sap["is_close"] is True
    assert sap["delayed"] is True
    assert sap["timestamp"].startswith("2026-10-30")
    assert "error" not in sap


async def test_normal_quotes_are_not_marked_as_close(monkeypatch):
    quotes = await first_quotes(FakeMarket(), monkeypatch)
    aapl = quotes["AAPL"]
    assert aapl["value"] == 344.63
    assert aapl["source"] == "finnhub"
    assert aapl.get("is_close") is not True


async def test_fallback_reuses_the_chart_history_cache_key(monkeypatch):
    market = FakeMarket()
    await first_quotes(market, monkeypatch)
    # Même durée que le graphique (30 jours) : une seule entrée de cache,
    # donc un seul appel EODHD.
    assert market.history_calls == [("SAP.DE", 30)]


async def test_when_the_history_fails_too_the_original_error_is_kept(monkeypatch):
    market = FakeMarket(history_error=MarketDataError("eodhd", "HTTP 404"))
    quotes = await first_quotes(market, monkeypatch)
    sap = quotes["SAP.DE"]
    assert "HTTP 429 pour SAP.DE" in sap["error"]
    assert sap.get("is_close") is not True
    assert "value" not in sap


@pytest.mark.parametrize("symbols", ["AAPL"])
async def test_no_history_call_when_the_quote_works(monkeypatch, symbols):
    market = FakeMarket()
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "APP_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "x")
    app = create_app(portfolio_service=FakePortfolio(), llm=object(), market=market)
    transport = httpx.ASGITransport(app=app)
    url = f"/market/stream?symbols={symbols}&interval=0.05&max_events=1"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", url) as response:
            async for _ in response.aiter_text():
                pass
    assert market.history_calls == []
