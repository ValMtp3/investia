"""Tests de la façade MarketService : routeur + cache Redis."""

from datetime import UTC, datetime

import pytest

from investia.market.base import MarketData
from investia.market.service import MarketService


class FakeConnector:
    name = "finnhub"

    def __init__(self):
        self.quote_calls = 0

    async def get_quote(self, symbol: str) -> MarketData:
        self.quote_calls += 1
        return MarketData(
            value=100.0 + self.quote_calls,
            currency="USD",
            source=self.name,
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol: str, days: int = 30):
        return []

    async def get_news(self, symbol: str, limit: int = 5):
        return []


@pytest.fixture
def fake_redis(monkeypatch):
    import investia.market.cache as cache_module

    class FakeRedis:
        def __init__(self):
            self.store = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            self.store[key] = value

    fake = FakeRedis()
    monkeypatch.setattr(cache_module, "get_redis", lambda: fake)
    return fake


async def test_get_quote_uses_router_and_caches(fake_redis):
    finnhub = FakeConnector()
    service = MarketService(connectors={"finnhub": finnhub})
    q1 = await service.get_quote("AAPL")
    q2 = await service.get_quote("AAPL")
    assert q1 == q2
    assert finnhub.quote_calls == 1, "le 2e appel doit venir du cache"
    assert q1.source == "finnhub"


async def test_get_quote_europe_picks_yahoo_connector(fake_redis):
    class YahooFake(FakeConnector):
        name = "yahoo"

    yahoo = YahooFake()
    service = MarketService(connectors={"yahoo": yahoo})
    quote = await service.get_quote("SAP.DE")
    assert quote.source == "yahoo"
    assert yahoo.quote_calls == 1


async def test_without_cache_every_call_hits_connector(fake_redis):
    finnhub = FakeConnector()
    service = MarketService(connectors={"finnhub": finnhub}, use_cache=False)
    await service.get_quote("AAPL")
    await service.get_quote("AAPL")
    assert finnhub.quote_calls == 2
