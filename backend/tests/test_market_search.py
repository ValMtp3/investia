"""Tests de la recherche de symboles (GET /market/search) — autocomplétion /marche.

Contrat : MarketService.search_symbols interroge les connecteurs qui supportent
la recherche (finnhub, yahoo, coingecko) en cascade, fusionne et dédoublonne par
symbole. La route valide q (2-30 car.) et limit (1-20).
"""

import httpx
import pytest

from investia.market.base import MarketDataError, SymbolHit
from investia.market.service import MarketService


class FakeConnector:
    def __init__(self, name, hits=None, error=None):
        self.name = name
        self._hits = hits or []
        self._error = error
        self.calls = 0

    async def get_quote(self, symbol):
        raise NotImplementedError

    async def get_history(self, symbol, days=30):
        raise NotImplementedError

    async def get_news(self, symbol, limit=5):
        raise NotImplementedError

    async def search_symbols(self, query, limit=10):
        self.calls += 1
        if self._error:
            raise self._error
        return self._hits[:limit]


HITS_FINNHUB = [
    SymbolHit(
        symbol="AAPL", description="Apple Inc.", type="Common Stock", source="finnhub"
    ),
    SymbolHit(
        symbol="MSFT", description="Microsoft", type="Common Stock", source="finnhub"
    ),
]
HITS_YAHOO = [
    SymbolHit(symbol="AAPL", description="Apple Inc.", type="EQUITY", source="yahoo"),
    SymbolHit(symbol="SAP.DE", description="SAP SE", type="EQUITY", source="yahoo"),
]
HITS_COINGECKO = [
    SymbolHit(
        symbol="BTC-USD", description="Bitcoin", type="crypto", source="coingecko"
    ),
]


async def test_search_merges_and_dedupes_across_sources():
    svc = MarketService(
        {
            "finnhub": FakeConnector("finnhub", HITS_FINNHUB),
            "yahoo": FakeConnector("yahoo", HITS_YAHOO),
            "coingecko": FakeConnector("coingecko", HITS_COINGECKO),
        },
        use_cache=False,
    )
    results = await svc.search_symbols("apple", limit=10)
    symbols = [r.symbol for r in results]
    assert symbols == ["AAPL", "MSFT", "SAP.DE", "BTC-USD"]  # AAPL dédoublonné
    assert results[0].source == "finnhub"  # la première source garde la tête


async def test_search_skips_failing_source_and_keeps_going():
    svc = MarketService(
        {
            "finnhub": FakeConnector(
                "finnhub", error=MarketDataError("finnhub", "HTTP 500")
            ),
            "yahoo": FakeConnector("yahoo", HITS_YAHOO),
        },
        use_cache=False,
    )
    results = await svc.search_symbols("sap", limit=10)
    assert [r.symbol for r in results] == ["AAPL", "SAP.DE"]


async def test_search_all_sources_down_raises_clear_error():
    svc = MarketService(
        {
            "finnhub": FakeConnector(
                "finnhub", error=MarketDataError("finnhub", "HTTP 500")
            ),
            "yahoo": FakeConnector(
                "yahoo", error=MarketDataError("yahoo", "HTTP 429", rate_limited=True)
            ),
        },
        use_cache=False,
    )
    with pytest.raises(MarketDataError, match="recherche"):
        await svc.search_symbols("apple")


async def test_search_limit_is_respected():
    many = [
        SymbolHit(
            symbol=f"S{i}", description=f"Société {i}", type="EQUITY", source="finnhub"
        )
        for i in range(10)
    ]
    svc = MarketService({"finnhub": FakeConnector("finnhub", many)}, use_cache=False)
    results = await svc.search_symbols("s", limit=3)
    assert len(results) == 3


# --- Route GET /market/search ---


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    from investia.main import create_app

    svc = MarketService(
        {
            "finnhub": FakeConnector("finnhub", HITS_FINNHUB),
            "yahoo": FakeConnector("yahoo", HITS_YAHOO),
        },
        use_cache=False,
    )

    class FakePortfolio:
        async def get_portfolio(self):
            return {}

        async def place_order(self, *a):
            return {}

        async def adjust_capital(self, *a):
            return {}

    class FakeLlm:
        async def chat(self, *a, **k):
            raise NotImplementedError

    class FakeTrace:
        async def list_runs(self, limit=50):
            return []

        async def get_run(self, rid):
            return {"run": None, "steps": []}

    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlm(),
        market=svc,
        trace_store=FakeTrace(),
    )


async def test_route_market_search_returns_results(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/market/search", params={"q": "apple", "limit": 5})
        assert resp.status_code == 200
        body = resp.json()
        symbols = [r["symbol"] for r in body["results"]]
        assert "AAPL" in symbols and "SAP.DE" in symbols
        first = body["results"][0]
        assert set(first) >= {"symbol", "description", "type", "source"}


async def test_route_market_search_validates_query(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (
            await client.get("/market/search", params={"q": "a"})
        ).status_code == 422
        assert (await client.get("/market/search")).status_code == 422
        assert (
            await client.get("/market/search", params={"q": "apple", "limit": 99})
        ).status_code == 422
