"""Tests de l'outil simulate_order (spec 5.1) et de son enregistrement conditionnel."""

import pytest

from investia.tools import build_tools
from investia.tools.base import ToolError
from investia.tools.order import SimulateOrderTool


class FakeMarket:
    async def get_quote(self, symbol):
        raise NotImplementedError

    async def get_history(self, symbol, days=30):
        raise NotImplementedError

    async def get_news(self, symbol, limit=5):
        raise NotImplementedError


ORDER_RESULT = {
    "order_id": "ord-1",
    "symbol": "AAPL",
    "side": "buy",
    "quantity": 3.0,
    "price": 344.63,
    "fees": 10.34,
    "currency": "EUR",
}


class FakePortfolioService:
    def __init__(self, result=None, error=None):
        self._result = ORDER_RESULT if result is None else result
        self._error = error
        self.calls: list[tuple[str, str, float]] = []

    async def place_order(self, symbol, side, quantity):
        if self._error is not None:
            raise self._error
        self.calls.append((symbol, side, quantity))
        return self._result

    async def get_portfolio(self):
        raise NotImplementedError


def make_tool(service=None):
    return SimulateOrderTool(service or FakePortfolioService())


async def test_simulate_order_executes_place_order_and_returns_result():
    service = FakePortfolioService()
    tool = make_tool(service)
    args = tool.args_schema.model_validate(
        {"symbol": "aapl", "side": "buy", "quantity": 3}
    )
    result = await tool.run(args)
    assert result == ORDER_RESULT
    # symbole normalisé en majuscules comme POST /orders
    assert service.calls == [("AAPL", "buy", 3.0)]


async def test_simulate_order_wraps_errors_as_tool_error():
    tool = make_tool(FakePortfolioService(error=RuntimeError("db down")))
    args = tool.args_schema.model_validate(
        {"symbol": "AAPL", "side": "sell", "quantity": 1}
    )
    with pytest.raises(ToolError, match="simulate_order"):
        await tool.run(args)


def test_simulate_order_llm_contract():
    spec = make_tool().to_openai_tool()
    assert spec["function"]["name"] == "simulate_order"
    params = spec["function"]["parameters"]
    assert set(params["properties"]) == {"symbol", "side", "quantity"}
    assert set(params["required"]) == {"symbol", "side", "quantity"}
    assert params["properties"]["side"]["enum"] == ["buy", "sell"]
    assert params["properties"]["quantity"]["exclusiveMinimum"] == 0


def test_simulate_order_rejects_bad_side_and_quantity():
    tool = make_tool()
    with pytest.raises(Exception):
        tool.args_schema.model_validate(
            {"symbol": "AAPL", "side": "hold", "quantity": 1}
        )
    with pytest.raises(Exception):
        tool.args_schema.model_validate(
            {"symbol": "AAPL", "side": "buy", "quantity": 0}
        )
    with pytest.raises(Exception):
        tool.args_schema.model_validate(
            {"symbol": "AAPL", "side": "buy", "quantity": -2}
        )


def test_build_tools_registers_simulate_order_only_when_service_provided():
    assert "simulate_order" not in build_tools(FakeMarket())
    tools = build_tools(FakeMarket(), portfolio_service=FakePortfolioService())
    assert tools["simulate_order"].name == "simulate_order"
    # get_portfolio et les 4 outils marché restent présents
    assert "get_portfolio" in tools
    assert {"get_quote", "get_history", "get_indicators", "get_news"} <= set(tools)
