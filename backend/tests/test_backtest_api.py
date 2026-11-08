"""TDD étape 10 : route GET /portfolio/backtest + BacktestService (fakes, zéro base)."""

from datetime import UTC, datetime

import httpx

from investia.main import create_app
from investia.market.base import MarketData, MarketDataError
from investia.portfolio.backtest import BacktestAdjustment, BacktestOrder
from investia.portfolio.backtest_service import BacktestService

ADMIN_SECRET = "test-admin-secret-0123456789abcdef"

BACKTEST_PAYLOAD = {
    "start_date": "2026-10-30",
    "initial_capital": 10_000.0,
    "benchmark_symbol": "CW8.PA",
    "points": [
        {"date": "2026-10-30", "portfolio_value": 9_999.0, "benchmark_value": 10_000.0},
        {
            "date": "2026-10-31",
            "portfolio_value": 10_099.0,
            "benchmark_value": 11_000.0,
        },
    ],
    "perf_portfolio_pct": 0.99,
    "perf_benchmark_pct": 10.0,
    "warnings": [],
    "generated_at": "2026-11-08T10:00:00+00:00",
}


class FakeBacktestService:
    def __init__(self, payload=None, error=None):
        self._payload = payload if payload is not None else BACKTEST_PAYLOAD
        self._error = error
        self.calls = 0

    async def compute(self):
        self.calls += 1
        if self._error:
            raise self._error
        return self._payload


class FakeMarket:
    """Historique déterministe : CW8.PA et AAA.PA en EUR, USD->EUR à 0,9."""

    async def get_history(self, symbol, days=30):
        if symbol == "CW8.PA":
            return [
                MarketData(100.0, "EUR", "eodhd", datetime(2026, 10, 30, tzinfo=UTC)),
                MarketData(110.0, "EUR", "eodhd", datetime(2026, 10, 31, tzinfo=UTC)),
            ]
        if symbol == "AAA.PA":
            return [
                MarketData(100.0, "EUR", "eodhd", datetime(2026, 10, 30, tzinfo=UTC)),
                MarketData(110.0, "EUR", "eodhd", datetime(2026, 10, 31, tzinfo=UTC)),
            ]
        if symbol == "USD":
            return [
                MarketData(
                    0.9, "EUR", "frankfurter", datetime(2026, 10, 30, tzinfo=UTC)
                )
            ]
        raise MarketDataError("fake", f"pas d'historique pour {symbol}")

    async def get_quote(self, symbol):
        raise MarketDataError("fake", "pas de quote")

    async def get_news(self, symbol, limit=5):
        return []

    async def search_symbols(self, query, limit=10):
        return []


def make_client(monkeypatch, backtest_service) -> httpx.AsyncClient:
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", ADMIN_SECRET)
    app = create_app(
        portfolio_service=object(),
        llm=object(),
        market=FakeMarket(),
        backtest_service=backtest_service,
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_backtest_route_returns_payload(monkeypatch):
    service = FakeBacktestService()
    client = make_client(monkeypatch, service)
    response = await client.get("/portfolio/backtest")
    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_symbol"] == "CW8.PA"
    assert body["perf_benchmark_pct"] == 10.0
    assert len(body["points"]) == 2
    assert service.calls == 1


async def test_backtest_route_503_when_service_missing(monkeypatch):
    client = make_client(monkeypatch, None)
    response = await client.get("/portfolio/backtest")
    assert response.status_code == 503
    assert "backtest" in response.json()["detail"]


async def test_backtest_route_503_when_benchmark_history_fails(monkeypatch):
    service = FakeBacktestService(
        error=MarketDataError("backtest", "indice indisponible")
    )
    client = make_client(monkeypatch, service)
    response = await client.get("/portfolio/backtest")
    assert response.status_code == 503
    assert "indice" in response.json()["detail"]


def _service_with_events(monkeypatch, orders, adjustments, market=None):
    service = BacktestService(
        session_factory=None, market=market or FakeMarket(), use_cache=False
    )

    async def fake_load_events():
        return orders, adjustments

    monkeypatch.setattr(service, "_load_events", fake_load_events)
    return service


async def test_service_computes_backtest_from_events(monkeypatch):
    orders = [
        BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=10)
    ]
    adjustments = [BacktestAdjustment(date="2026-10-30", amount=10_000.0)]
    service = _service_with_events(monkeypatch, orders, adjustments)
    result = await service.compute()
    assert result["start_date"] == "2026-10-30"
    assert result["initial_capital"] == 10_000.0
    assert result["benchmark_symbol"] == "CW8.PA"
    by_date = {p["date"]: p for p in result["points"]}
    assert by_date["2026-10-30"]["portfolio_value"] == 9_999.0
    assert by_date["2026-10-31"]["portfolio_value"] == 10_099.0
    assert by_date["2026-10-31"]["benchmark_value"] == 11_000.0
    assert result["perf_benchmark_pct"] == 10.0
    assert result["warnings"] == []
    assert result["generated_at"]


async def test_service_without_events_returns_empty_result(monkeypatch):
    service = _service_with_events(monkeypatch, [], [])
    result = await service.compute()
    assert result["points"] == []
    assert result["start_date"] is None
    assert any("Aucun ordre" in w for w in result["warnings"])


async def test_service_warns_when_symbol_history_missing(monkeypatch):
    orders = [BacktestOrder(date="2026-10-30", symbol="ZZZ.PA", side="buy", quantity=1)]
    adjustments = [BacktestAdjustment(date="2026-10-30", amount=10_000.0)]
    service = _service_with_events(monkeypatch, orders, adjustments)
    result = await service.compute()
    # ZZZ.PA sans historique : ordre ignoré, portefeuille = cash, warning émis
    assert any("ZZZ.PA" in w for w in result["warnings"])
    assert result["points"][-1]["portfolio_value"] == 10_000.0


async def test_service_works_with_cache_enabled_and_redis_down(monkeypatch):
    """Redis indisponible : cached() calcule quand même (Redis = optimisation)."""
    orders = [
        BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=10)
    ]
    adjustments = [BacktestAdjustment(date="2026-10-30", amount=10_000.0)]
    service = _service_with_events(monkeypatch, orders, adjustments)
    service._use_cache = True
    result = await service.compute()
    assert result["perf_benchmark_pct"] == 10.0
