"""Tests de la boucle d'agent (run_agent) — LLM et marché fake, zéro réseau."""

from datetime import UTC, datetime
from typing import Any

import pytest

from investia.agent import run_agent
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData, MarketDataError
from investia.tools import build_tools


class FakeLlm:
    """LLM fake : rejoue une liste de réponses, mémorise les appels."""

    def __init__(self, responses: list[LlmResponse]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        self.calls.append(
            {"model": model_key, "messages": list(messages), "tools": tools}
        )
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class FakeMarket:
    def __init__(self, quote=None, error=None):
        self._quote = quote
        self._error = error

    async def get_quote(self, symbol):
        if self._error:
            raise self._error
        return self._quote

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


def make_response(content="", tool_calls=None, cost=0.01):
    return LlmResponse(
        content=content,
        model="gpt-6-luna",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


def quote_tool_call(symbol="AAPL"):
    return [ToolCall(id="call_1", name="get_quote", arguments={"symbol": symbol})]


# Réponses finales conformes aux garde-fous (2.1) : 4 sections + disclaimer + sourcé.
FINAL_WITH_PRICE = """## Thèse
Le prix de AAPL est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

FINAL_NO_NUMBER = """## Thèse
La source est indisponible pour l'instant.

## Risques
aucun.

## Confiance
50

## Sources
- aucune

Simulation — pas un conseil en investissement.
"""


async def test_full_scenario_tool_then_final_answer():
    quote = MarketData(
        value=344.63,
        currency="USD",
        source="finnhub",
        timestamp=datetime(2026, 10, 31, tzinfo=UTC),
    )
    llm = FakeLlm(
        [
            make_response(tool_calls=quote_tool_call()),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    tools = build_tools(FakeMarket(quote=quote))
    result = await run_agent("prix de AAPL ?", llm, tools)
    assert "344.63" in result.answer
    assert result.turns == 2
    assert [c.tool for c in result.tool_calls] == ["get_quote"]
    # le 2e appel au LLM contient le résultat de l'outil en role=tool
    second_call_messages = llm.calls[1]["messages"]
    tool_messages = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "344.63" in tool_messages[0]["content"]
    assert result.total_cost_cents == pytest.approx(0.02)


async def test_max_turns_stops_cleanly():
    quote = MarketData(
        value=1.0,
        currency="USD",
        source="finnhub",
        timestamp=datetime(2026, 10, 31, tzinfo=UTC),
    )
    llm = FakeLlm([make_response(tool_calls=quote_tool_call())])  # boucle infinie
    tools = build_tools(FakeMarket(quote=quote))
    result = await run_agent("boucle ?", llm, tools, max_turns=3)
    assert result.turns == 3
    assert "tours" in result.answer


async def test_tool_error_is_sent_back_to_model_not_swallowed():
    llm = FakeLlm(
        [
            make_response(tool_calls=quote_tool_call()),
            make_response(content=FINAL_NO_NUMBER),
        ]
    )
    tools = build_tools(FakeMarket(error=MarketDataError("finnhub", "HTTP 500")))
    result = await run_agent("prix AAPL ?", llm, tools)
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "finnhub" in tool_messages[0]["content"]
    assert "500" in tool_messages[0]["content"]
    assert result.turns == 2


async def test_invalid_tool_args_are_reported_to_model():
    llm = FakeLlm(
        [
            make_response(tool_calls=quote_tool_call(symbol="   ")),
            make_response(content=FINAL_NO_NUMBER),
        ]
    )
    tools = build_tools(FakeMarket())
    await run_agent("prix ?", llm, tools)
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "symbole" in tool_messages[0]["content"].lower()


async def test_unknown_tool_is_reported():
    llm = FakeLlm(
        [
            make_response(tool_calls=[ToolCall(id="c1", name="bidule", arguments={})]),
            make_response(content=FINAL_NO_NUMBER),
        ]
    )
    tools = build_tools(FakeMarket())
    await run_agent("?", llm, tools)
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "inconnu" in tool_messages[0]["content"]
