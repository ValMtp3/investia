"""Tests des routes de lecture des traces et evals (spec 4.5)."""

from datetime import UTC, datetime

import httpx

from investia.main import create_app
from investia.market.base import MarketData


class FakeMarket:
    async def get_quote(self, symbol):
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


class FakePortfolio:
    async def get_portfolio(self):
        return {}


class FakeTraceStore:
    """Faux store de traces : liste et détail fixés à l'avance."""

    def __init__(self, runs=None, run_detail=None):
        self._runs = runs or []
        self._run_detail = run_detail
        self.list_calls: list[int] = []

    async def list_runs(self, limit=50):
        self.list_calls.append(limit)
        return self._runs[:limit]

    async def get_run(self, run_id):
        return self._run_detail


class FakeEvalStore:
    def __init__(self, payload=None):
        self._payload = payload or {"runs": []}

    async def list_eval_runs(self):
        return self._payload


def make_client(monkeypatch, trace_store, eval_store) -> httpx.AsyncClient:
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
    ):
        monkeypatch.setenv(var, "x")
    app = create_app(
        portfolio_service=FakePortfolio(),
        llm=object(),
        market=FakeMarket(),
        trace_store=trace_store,
        eval_store=eval_store,
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


RUN_A = {
    "id": "11111111-1111-1111-1111-111111111111",
    "question": "prix AAPL ?",
    "status": "ok",
    "model": "gpt-6-luna",
    "turns": 2,
    "total_cost_cents": 0.03,
    "created_at": "2026-11-05T10:00:00+00:00",
}
RUN_B = {
    "id": "22222222-2222-2222-2222-222222222222",
    "question": "SAP.DE en hausse ?",
    "status": "blocked",
    "model": "elephant",
    "turns": 3,
    "total_cost_cents": 0.0,
    "created_at": "2026-11-04T09:30:00+00:00",
}


async def test_get_traces_returns_runs_from_store(monkeypatch):
    store = FakeTraceStore(runs=[RUN_A, RUN_B])
    client = make_client(monkeypatch, store, FakeEvalStore())
    response = await client.get("/traces")
    assert response.status_code == 200
    assert response.json() == {"runs": [RUN_A, RUN_B]}
    assert store.list_calls == [50]


async def test_get_traces_limit_is_forwarded_and_bounded(monkeypatch):
    store = FakeTraceStore(runs=[RUN_A, RUN_B])
    client = make_client(monkeypatch, store, FakeEvalStore())
    response = await client.get("/traces", params={"limit": 1})
    assert response.status_code == 200
    assert response.json() == {"runs": [RUN_A]}
    assert store.list_calls == [1]
    for bad in (0, 201):
        response = await client.get("/traces", params={"limit": bad})
        assert response.status_code == 422


TRACE_DETAIL = {
    "run": {**RUN_A, "answer": "AAPL vaut 344.63 $ (source : finnhub)."},
    "steps": [
        {
            "turn": 1,
            "kind": "llm_call",
            "payload": {"model": "gpt-6-luna", "cost_cents": 0.01},
            "created_at": "2026-11-05T10:00:01+00:00",
        },
        {
            "turn": 1,
            "kind": "tool_call",
            "payload": {"name": "get_quote", "ok": True},
            "created_at": "2026-11-05T10:00:02+00:00",
        },
    ],
}


async def test_get_trace_returns_run_and_steps(monkeypatch):
    store = FakeTraceStore(run_detail=TRACE_DETAIL)
    client = make_client(monkeypatch, store, FakeEvalStore())
    response = await client.get(f"/traces/{RUN_A['id']}")
    assert response.status_code == 200
    assert response.json() == TRACE_DETAIL


async def test_get_trace_unknown_run_returns_404(monkeypatch):
    store = FakeTraceStore(run_detail={"run": None, "steps": []})
    client = make_client(monkeypatch, store, FakeEvalStore())
    response = await client.get(f"/traces/{RUN_A['id']}")
    assert response.status_code == 404
    assert "inconnu" in response.json()["detail"]


async def test_get_trace_invalid_uuid_returns_422(monkeypatch):
    client = make_client(monkeypatch, FakeTraceStore(), FakeEvalStore())
    response = await client.get("/traces/pas-un-uuid")
    assert response.status_code == 422


EVALS_PAYLOAD = {
    "runs": [
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "started_at": "2026-11-05T09:00:00+00:00",
            "model": "gpt-6-luna",
            "commit": "abc1234",
            "mode": "mock",
            "results": [
                {"case_id": "q1", "metric": "tool_used", "score": 1.0},
                {"case_id": "q1", "metric": "disclaimer", "score": 1.0},
                {"case_id": "q2", "metric": "tool_used", "score": 0.0},
            ],
        }
    ]
}


async def test_get_evals_returns_eval_runs_with_results(monkeypatch):
    client = make_client(monkeypatch, FakeTraceStore(), FakeEvalStore(EVALS_PAYLOAD))
    response = await client.get("/evals")
    assert response.status_code == 200
    assert response.json() == EVALS_PAYLOAD


async def test_read_routes_return_503_when_stores_are_not_injected(monkeypatch):
    """Sans stores injectés, les routes de lecture renvoient un 503 clair."""
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
    ):
        monkeypatch.setenv(var, "x")
    app = create_app(
        portfolio_service=FakePortfolio(), llm=object(), market=FakeMarket()
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    for path in ("/traces", "/traces/11111111-1111-1111-1111-111111111111", "/evals"):
        response = await client.get(path)
        assert response.status_code == 503, path
        assert "detail" in response.json()
