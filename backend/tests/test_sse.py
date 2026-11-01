"""Tests des routes SSE : POST /agent/run et GET /market/stream (flux mockés)."""

from datetime import UTC, datetime

import httpx
import pytest

from investia.llm.client import LlmResponse, ToolCall
from investia.main import create_app
from investia.market.base import MarketData

FINAL_OK = """## Thèse
AAPL vaut 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


class FakeLlm:
    def __init__(self):
        self._responses = [
            LlmResponse(
                content="",
                model="gpt-6-luna",
                prompt_tokens=10,
                completion_tokens=5,
                cost_cents=0.01,
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            ),
            LlmResponse(
                content=FINAL_OK,
                model="gpt-6-luna",
                prompt_tokens=20,
                completion_tokens=50,
                cost_cents=0.02,
            ),
        ]

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


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
    async def ensure_default_portfolio(self):
        return "p1"

    async def get_portfolio(self):
        return {
            "cash": 10_000.0,
            "positions": [],
            "total_value": 10_000.0,
            "currency": "EUR",
        }

    async def place_order(self, symbol, side, quantity):
        return {"ok": True}

    async def adjust_capital(self, amount, reason):
        return {"cash": 10_000.0 + amount}


@pytest.fixture
def app(monkeypatch):
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "APP_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "x")
    return create_app(
        portfolio_service=FakePortfolio(), llm=FakeLlm(), market=FakeMarket()
    )


async def parse_sse_events(response: httpx.Response) -> list[tuple[str, dict]]:
    events = []
    event_name = "message"
    async for chunk in response.aiter_text():
        for block in chunk.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
            if data_lines:
                import json

                events.append((event_name, json.loads("\n".join(data_lines))))
    return events


async def test_agent_run_streams_events_in_order(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/agent/run", json={"question": "prix AAPL ?"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = await parse_sse_events(response)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "start"
    assert "llm_call" in kinds
    assert "tool_call" in kinds
    assert "guardrail" in kinds
    answer = next(payload for kind, payload in events if kind == "answer")
    assert "344.63" in answer["text"]
    assert kinds[-1] == "done"
    done = events[-1][1]
    assert done["turns"] >= 2
    assert "cost_cents" in done


async def test_market_stream_pushes_quotes(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.send(
            httpx.Request(
                "GET",
                "http://test/market/stream?symbols=AAPL&interval=0.05&max_events=2",
            ),
            stream=True,
        )
        assert response.status_code == 200
        seen = 0
        async for chunk in response.aiter_text():
            for block in chunk.split("\n\n"):
                if "event: quotes" in block:
                    seen += 1
            if seen >= 2:
                break
        await response.aclose()
        assert seen >= 2


async def test_market_stream_quotes_include_symbol_and_source(app):
    """Chaque quote du flux porte son symbole (le frontend associe prix -> symbole)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "GET",
            "/market/stream?symbols=AAPL,SAP.DE&interval=0.05&max_events=1",
        ) as response:
            events = await parse_sse_events(response)
    quotes_event = next(payload for kind, payload in events if kind == "quotes")
    quotes = quotes_event["quotes"]
    assert {q["symbol"] for q in quotes} == {"AAPL", "SAP.DE"}
    for quote in quotes:
        assert quote["value"] == 344.63
        assert quote["source"] == "finnhub"
        assert "timestamp" in quote


async def test_cors_allows_frontend_origin(app, monkeypatch):
    """Le dashboard en dev (localhost:5173) peut appeler l'API (sinon bloqué)."""
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    from investia.config import get_settings

    get_settings.cache_clear()
    app_with_cors = create_app(
        portfolio_service=FakePortfolio(), llm=FakeLlm(), market=FakeMarket()
    )
    transport = httpx.ASGITransport(app=app_with_cors)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"Origin": "http://localhost:5173"}
        )
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:5173"
        )
        preflight = await client.options(
            "/agent/run",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200
        assert "POST" in preflight.headers["access-control-allow-methods"]
