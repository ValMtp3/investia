"""Tests du serveur MCP Investia (spec 5.2, D58) : les 6 outils exposés via FastMCP."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastmcp import Client

from investia.main import create_app
from investia.market.base import MarketData
from investia.mcp_server import build_mcp_server


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 11, 7, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return [
            MarketData(
                value=100.0 + i,
                currency="USD",
                source="eodhd",
                timestamp=datetime(2026, 10, 1 + i, tzinfo=UTC),
            )
            for i in range(3)
        ]

    async def get_news(self, symbol, limit=5):
        return []


class FakePortfolio:
    def __init__(self):
        self.orders: list[tuple[str, str, float]] = []

    async def get_portfolio(self):
        return {
            "cash": 10_000.0,
            "positions": [],
            "positions_value": 0.0,
            "total_value": 10_000.0,
            "currency": "EUR",
        }

    async def place_order(self, symbol, side, quantity):
        self.orders.append((symbol, side, quantity))
        return {
            "order_id": "ord-1",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
        }

    async def adjust_capital(self, amount, reason):
        return {"cash": 10_000.0 + amount}


@pytest.fixture
def portfolio():
    return FakePortfolio()


async def test_lists_the_six_tools_with_their_input_schemas(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    tools = await mcp.list_tools()
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {
        "get_quote",
        "get_history",
        "get_indicators",
        "get_news",
        "get_portfolio",
        "simulate_order",
    }
    # schéma exposé = schéma interne (pas de doublon qui dérive)
    assert set(by_name["get_quote"].parameters["properties"]) == {"symbol"}
    assert set(by_name["simulate_order"].parameters["properties"]) == {
        "symbol",
        "side",
        "quantity",
    }
    assert by_name["simulate_order"].parameters["properties"]["side"]["enum"] == [
        "buy",
        "sell",
    ]
    assert by_name["get_portfolio"].parameters["properties"] == {}


async def test_call_get_quote_returns_price_with_source_and_timestamp(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp) as client:
        result = await client.call_tool("get_quote", {"symbol": "AAPL"})
    payload = json.loads(result.content[0].text)
    assert payload["value"] == 344.63
    assert payload["source"] == "finnhub"
    assert "timestamp" in payload


async def test_call_get_portfolio_returns_portfolio(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp) as client:
        result = await client.call_tool("get_portfolio", {})
    payload = json.loads(result.content[0].text)
    assert payload["total_value"] == 10_000.0
    assert payload["currency"] == "EUR"


async def test_call_simulate_order_executes_the_simulated_order(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp) as client:
        result = await client.call_tool(
            "simulate_order", {"symbol": "AAPL", "side": "buy", "quantity": 3}
        )
    payload = json.loads(result.content[0].text)
    assert payload["order_id"] == "ord-1"
    assert portfolio.orders == [("AAPL", "buy", 3.0)]


async def test_tool_error_is_returned_as_readable_error_not_internal_detail(portfolio):
    class FailingMarket(FakeMarket):
        async def get_quote(self, symbol):
            raise RuntimeError("db down secret detail")

    mcp = build_mcp_server(FailingMarket(), portfolio)
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_quote", {"symbol": "AAPL"}, raise_on_error=False
        )
    # isError + message générique : le détail interne ne fuite pas au client MCP
    assert result.is_error
    text = result.content[0].text
    assert "secret detail" not in text


async def test_invalid_arguments_are_rejected(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp) as client:
        result = await client.call_tool(
            "simulate_order",
            {"symbol": "AAPL", "side": "hold", "quantity": 1},
            raise_on_error=False,
        )
    assert result.is_error


@pytest.fixture
def app(monkeypatch, portfolio):
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
    ):
        monkeypatch.setenv(
            var,
            "postgresql+asyncpg://u:p@localhost/db"
            if var == "DATABASE_URL"
            else (
                "redis://localhost:6379/0"
                if var == "REDIS_URL"
                else (
                    "http://localhost:4000" if var == "LITELLM_BASE_URL" else "sk-test"
                )
            ),
        )
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")

    class FakeLlm:
        async def chat(self, *a, **k):
            raise NotImplementedError

    class FakeTraceStore:
        async def list_runs(self, limit=50):
            return []

        async def get_run(self, run_id):
            return {"run": None, "steps": []}

    return create_app(
        portfolio_service=portfolio,
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=FakeTraceStore(),
    )


MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


async def test_http_endpoint_mcp_answers_initialize_and_tools_list(app):
    """POST /mcp/ (streamable HTTP) : initialize puis tools/list renvoient les 6 outils.

    ASGITransport ne lance pas le lifespan : on ouvre seulement celui du sous-app
    MCP monté sur /mcp (requis pour sa session manager), sans toucher au lifespan
    global de l'app (qui fermerait le singleton DB partagé avec les autres tests).
    """
    transport = httpx.ASGITransport(app=app)
    mount = next(r for r in app.routes if getattr(r, "path", None) == "/mcp")
    mcp_app = mount.app
    async with mcp_app.lifespan(mcp_app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            init = await client.post(
                "/mcp/",
                headers=MCP_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                },
            )
            assert init.status_code == 200
            session_id = init.headers.get("mcp-session-id")

            headers = dict(MCP_HEADERS)
            if session_id:
                headers["mcp-session-id"] = session_id
            listing = await client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            assert listing.status_code == 200
            body = listing.text
            # la réponse peut être SSE (event: message / data: {...}) ou JSON
            data = body
            if "data:" in body:
                data = "\n".join(
                    line[len("data:") :].strip()
                    for line in body.splitlines()
                    if line.startswith("data:")
                )
            payload = json.loads(data)
            names = {t["name"] for t in payload["result"]["tools"]}
            assert {
                "get_quote",
                "get_history",
                "get_indicators",
                "get_news",
                "get_portfolio",
                "simulate_order",
            } <= names
