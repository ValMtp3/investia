"""Tests d'intégration des garde-fous dans la boucle d'agent."""

from datetime import UTC, datetime
from typing import Any

from investia.agent import run_agent
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        self.calls.append({"messages": list(messages)})
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


def resp(content, tool_calls=None):
    return LlmResponse(
        content=content,
        model="gpt-6-luna",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=0.01,
        tool_calls=tool_calls or [],
    )


BAD_ANSWER = """## Thèse
AAPL vaut 999999 $.

## Risques
aucun.

## Confiance
90

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

GOOD_ANSWER = """## Thèse
AAPL vaut 344.63 $.

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


async def test_invented_number_is_blocked_then_model_corrects():
    llm = FakeLlm(
        [
            resp(
                "",
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            ),
            resp(BAD_ANSWER),  # réponse finale avec chiffre inventé
            resp(GOOD_ANSWER),  # correction après le garde-fou
        ]
    )
    tools = build_tools(FakeMarket())
    result = await run_agent("prix AAPL ?", llm, tools)
    assert "344.63" in result.answer
    assert "999999" not in result.answer
    # le dernier appel au LLM a reçu le détail du garde-fou
    last_messages = llm.calls[-1]["messages"]
    guardrail_msgs = [m for m in last_messages if "garde-fou" in m["content"].lower()]
    assert guardrail_msgs, "le modèle doit recevoir le détail du garde-fou"
    assert any(not g.ok for g in result.guardrails)


async def test_answer_still_bad_after_corrections_is_refused():
    llm = FakeLlm(
        [
            resp(
                "",
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            ),
            resp(BAD_ANSWER),
            resp(BAD_ANSWER),  # 1ere correction, toujours faux
            resp(BAD_ANSWER),  # 2e correction, toujours faux
        ]
    )
    tools = build_tools(FakeMarket())
    result = await run_agent("prix AAPL ?", llm, tools, max_corrections=2)
    assert "bloquée" in result.answer.lower()
