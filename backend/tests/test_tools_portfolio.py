"""Tests de l'outil get_portfolio (spec 4.6) et de son enregistrement conditionnel."""

import pytest

from investia.tools import build_tools
from investia.tools.base import ToolError
from investia.tools.portfolio import GetPortfolioTool


class FakeMarket:
    async def get_quote(self, symbol):
        raise NotImplementedError

    async def get_history(self, symbol, days=30):
        raise NotImplementedError

    async def get_news(self, symbol, limit=5):
        raise NotImplementedError


PORTFOLIO = {
    "cash": 10_000.0,
    "positions": [
        {
            "symbol": "AAPL",
            "quantity": 10.0,
            "avg_price": 200.0,
            "price_eur": 180.0,
            "value_eur": 1_800.0,
            "source": "finnhub",
            "price_timestamp": "2026-11-05T10:00:00+00:00",
        }
    ],
    "positions_value": 1_800.0,
    "total_value": 11_800.0,
    "currency": "EUR",
}


class FakePortfolioService:
    def __init__(self, payload=None, error=None):
        self._payload = PORTFOLIO if payload is None else payload
        self._error = error

    async def get_portfolio(self):
        if self._error is not None:
            raise self._error
        return self._payload


async def test_get_portfolio_returns_service_state_unchanged():
    tool = GetPortfolioTool(FakePortfolioService())
    result = await tool.run(tool.args_schema.model_validate({}))
    assert result == PORTFOLIO


async def test_get_portfolio_wraps_service_errors_as_tool_error():
    tool = GetPortfolioTool(FakePortfolioService(error=RuntimeError("db down")))
    with pytest.raises(ToolError, match="get_portfolio"):
        await tool.run(tool.args_schema.model_validate({}))


def test_get_portfolio_llm_contract_has_no_required_argument():
    spec = GetPortfolioTool(FakePortfolioService()).to_openai_tool()
    assert spec["function"]["name"] == "get_portfolio"
    params = spec["function"]["parameters"]
    assert params["type"] == "object"
    assert params.get("required", []) == []
    assert params["properties"] == {}


def test_build_tools_registers_get_portfolio_only_when_service_provided():
    assert "get_portfolio" not in build_tools(FakeMarket())
    tools = build_tools(FakeMarket(), portfolio_service=FakePortfolioService())
    assert tools["get_portfolio"].name == "get_portfolio"
    # les 4 outils marché restent présents
    assert {"get_quote", "get_history", "get_indicators", "get_news"} <= set(tools)
