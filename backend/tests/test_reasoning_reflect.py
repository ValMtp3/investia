"""Tests TDD de la brique 12b : réflexion/auto-critique (reflect + boucle + evals)."""

import json
from typing import Any

import pytest

from investia.agent import run_agent
from investia.agent.reasoning import (
    Plan,
    PlanStep,
    ReflectionDecision,
    make_plan,
    parse_reflection,
    reflect,
)
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools
from datetime import UTC, datetime


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


def make_response(content="", tool_calls=None, cost=0.01):
    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


# --- Task 1 : parse_reflection / reflect ---


def test_parse_reflection_valid_ko():
    decision = parse_reflection('{"ok": false, "problemes": ["chiffre non sourcé"]}')
    assert decision.ok is False
    assert decision.problemes == ["chiffre non sourcé"]


def test_parse_reflection_valid_ok():
    decision = parse_reflection('{"ok": true, "problemes": []}')
    assert decision.ok is True
    assert decision.problemes == []


def test_parse_reflection_invalid_returns_ok_true():
    # Dégradé propre : illisible -> on laisse les garde-fous en code décider.
    decision = parse_reflection("pas du json")
    assert decision.ok is True
    assert decision.problemes == []


async def test_reflect_calls_llm_once_truncates_outputs_and_returns_cost():
    llm = FakeLlm([make_response(content='{"ok": true, "problemes": []}', cost=0.02)])
    big_output = "x" * 10_000
    decision, cost = await reflect(
        llm, "gpt-6-luna", "ma réponse", [big_output, "petite sortie"]
    )
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] is None
    sent = json.dumps(llm.calls[0]["messages"])
    assert len(sent) < 6000  # la grosse sortie a été tronquée
    assert "petite sortie" in sent
    assert decision.ok is True
    assert cost == 0.02


# --- Task 2 : boucle run_agent(reasoning="reflect" / "plan+reflect") ---


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


class FakeTraceStore:
    def __init__(self):
        self.steps = []
        self.finished = []

    async def start_run(self, question):
        return "run-1"

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append((run_id, turn, kind, payload))

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.finished.append({"status": status, "cost_cents": cost_cents})


FINAL_OK = """## Thèse
Le prix de AAPL est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

FINAL_BOGUEUX = """## Thèse
Le prix de AAPL est 999999 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

PLAN_JSON = json.dumps(
    {"steps": [{"step": "récupérer le prix de AAPL", "tool": "get_quote"}]}
)
REFLECT_OK = '{"ok": true, "problemes": []}'
REFLECT_KO = '{"ok": false, "problemes": ["chiffre 999999 non sourcé"]}'


def quote_call():
    return [ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})]


async def test_mode_none_aucune_reflection():
    llm = FakeLlm([make_response(tool_calls=quote_call()), make_response(content=FINAL_OK)])
    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    assert result.reflections == []
    assert len(llm.calls) == 2


async def test_mode_reflect_emits_event_logs_step_counts_cost():
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    store = FakeTraceStore()
    llm = FakeLlm(
        [
            make_response(tool_calls=quote_call(), cost=0.01),
            make_response(content=FINAL_OK, cost=0.01),
            make_response(content=REFLECT_OK, cost=0.02),
        ]
    )
    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        reasoning="reflect",
        trace_store=store,
        event_sink=sink,
    )
    assert len(result.reflections) == 1
    assert result.reflections[0].ok is True
    reflection_events = [p for k, p in events if k == "reflection"]
    assert len(reflection_events) == 1
    assert reflection_events[0]["ok"] is True
    assert any(s[2] == "reflection" for s in store.steps)
    assert result.total_cost_cents == pytest.approx(0.04)
    assert store.finished[0]["status"] == "ok"


async def test_mode_reflect_ko_declenche_correction_puis_ok():
    llm = FakeLlm(
        [
            make_response(tool_calls=quote_call(), cost=0.01),
            make_response(content=FINAL_BOGUEUX, cost=0.01),
            make_response(content=REFLECT_KO, cost=0.02),
            make_response(content=FINAL_OK, cost=0.01),
            make_response(content=REFLECT_OK, cost=0.02),
        ]
    )
    result = await run_agent(
        "prix de AAPL ?", llm, build_tools(FakeMarket()), reasoning="reflect"
    )
    assert [r.ok for r in result.reflections] == [False, True]
    assert result.reflections[0].problemes == ["chiffre 999999 non sourcé"]
    # le message de correction envoyé au modèle mentionne la réflexion
    correction_msgs = [
        m["content"]
        for call in llm.calls
        for m in call["messages"]
        if m["role"] == "user" and "Garde-fou" in str(m["content"])
    ]
    assert any("reflection" in c for c in correction_msgs)
    assert result.answer == FINAL_OK


async def test_mode_plan_reflect_combine():
    llm = FakeLlm(
        [
            make_response(content=PLAN_JSON, cost=0.02),
            make_response(tool_calls=quote_call(), cost=0.01),
            make_response(content=FINAL_OK, cost=0.01),
            make_response(content=REFLECT_OK, cost=0.01),
        ]
    )
    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        reasoning="plan+reflect",
    )
    assert result.plan is not None and result.plan.steps[0].tool == "get_quote"
    assert len(result.reflections) == 1
    assert result.total_cost_cents == pytest.approx(0.05)


async def test_mode_inconnu_rejete():
    llm = FakeLlm([make_response(content=FINAL_OK)])
    with pytest.raises(ValueError, match="reasoning"):
        await run_agent(
            "question", llm, build_tools(FakeMarket()), reasoning="plan+bidule"
        )
