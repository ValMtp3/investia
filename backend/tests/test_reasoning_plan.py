"""Tests TDD de la brique 12a : plan-and-execute (reasoning.py + boucle + evals)."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from investia.agent import run_agent
from investia.agent.reasoning import Plan, PlanStep, make_plan, parse_plan
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools

TOOLS = ["get_quote", "get_news", "get_history", "get_indicators", "get_portfolio"]

PLAN_JSON = json.dumps(
    {
        "steps": [
            {"step": "récupérer le prix de AAPL", "tool": "get_quote"},
            {"step": "rédiger la réponse", "tool": None},
        ]
    }
)


class FakeLlm:
    """LLM fake : rejoue une liste de réponses, mémorise les appels."""

    def __init__(self, responses: list[LlmResponse]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        self.calls.append(
            {"model": model_key, "messages": list(messages), "tools": tools}
        )
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def make_response(content="", tool_calls=None, cost=0.01):
    from investia.llm.client import ToolCall

    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


# --- Task 1 : parse_plan / make_plan ---


def test_parse_plan_valid_json():
    plan = parse_plan(PLAN_JSON, TOOLS)
    assert plan.steps == [
        PlanStep(step="récupérer le prix de AAPL", tool="get_quote"),
        PlanStep(step="rédiger la réponse", tool=None),
    ]


def test_parse_plan_invalid_json_returns_empty_plan():
    assert parse_plan("pas du json", TOOLS).steps == []
    assert parse_plan("", TOOLS).steps == []


def test_parse_plan_tool_inconnu_devient_none():
    plan = parse_plan('{"steps": [{"step": "x", "tool": "tool_inconnu"}]}', TOOLS)
    assert plan.steps[0].tool is None


def test_parse_plan_json_entoure_de_texte():
    text = f"Voici le plan :\n```json\n{PLAN_JSON}\n```\nBonne analyse."
    plan = parse_plan(text, TOOLS)
    assert len(plan.steps) == 2


async def test_make_plan_calls_llm_once_and_returns_cost():
    llm = FakeLlm([make_response(content=PLAN_JSON, cost=0.02)])
    plan, cost = await make_plan(llm, "gpt-6-luna", "Quel est le prix de AAPL ?", TOOLS)
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["model"] == "gpt-6-luna"
    assert cost == 0.02
    assert plan.steps[0].tool == "get_quote"
    assert plan.steps[1].tool is None


async def test_make_plan_invalid_llm_output_returns_empty_plan():
    llm = FakeLlm([make_response(content="je ne sais pas", cost=0.01)])
    plan, cost = await make_plan(llm, "gpt-6-luna", "question", TOOLS)
    assert plan.steps == []
    assert cost == 0.01


# --- Task 2 : boucle run_agent(reasoning=...) ---


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
        self.runs = []
        self.steps = []
        self.finished = []

    async def start_run(self, question):
        self.runs.append(question)
        return "run-1"

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append((run_id, turn, kind, payload))

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.finished.append(
            {
                "run_id": run_id,
                "answer": answer,
                "model": model,
                "turns": turns,
                "cost_cents": cost_cents,
                "status": status,
            }
        )


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


def quote_call():
    return [ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})]


async def test_mode_none_no_plan_call():
    llm = FakeLlm(
        [
            make_response(tool_calls=quote_call()),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    result = await run_agent(
        "Quel est le prix de AAPL ?", llm, build_tools(FakeMarket())
    )
    assert result.plan is None
    assert len(llm.calls) == 2  # tool_call + final, aucun appel de plan


async def test_mode_plan_emits_event_logs_step_and_counts_cost():
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    store = FakeTraceStore()
    llm = FakeLlm(
        [
            make_response(content=PLAN_JSON, cost=0.02),  # appel plan dédié
            make_response(tool_calls=quote_call(), cost=0.01),
            make_response(content=FINAL_WITH_PRICE, cost=0.01),
        ]
    )
    result = await run_agent(
        "Quel est le prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        reasoning="plan",
        trace_store=store,
        event_sink=sink,
    )
    assert result.plan is not None
    assert result.plan.steps[0].tool == "get_quote"
    plan_events = [p for k, p in events if k == "plan"]
    assert len(plan_events) == 1
    assert plan_events[0]["steps"][0]["tool"] == "get_quote"
    plan_steps = [s for s in store.steps if s[2] == "plan"]
    assert len(plan_steps) == 1
    assert plan_steps[0][1] == 0  # turn 0
    assert result.total_cost_cents == pytest.approx(0.04)  # 0.02 + 0.01 + 0.01
    assert store.finished[0]["status"] == "ok"


async def test_mode_plan_invalid_json_degrades_proprely():
    store = FakeTraceStore()
    llm = FakeLlm(
        [
            make_response(content="pas du json", cost=0.02),
            make_response(tool_calls=quote_call(), cost=0.01),
            make_response(content=FINAL_WITH_PRICE, cost=0.01),
        ]
    )
    result = await run_agent(
        "Quel est le prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        reasoning="plan",
        trace_store=store,
    )
    assert result.plan is not None
    assert result.plan.steps == []
    assert store.finished[0]["status"] == "ok"


async def test_reasoning_valeur_inconnue_rejetee():
    llm = FakeLlm([make_response(content=FINAL_WITH_PRICE)])
    with pytest.raises(ValueError, match="reasoning"):
        await run_agent(
            "question", llm, build_tools(FakeMarket()), reasoning="inconnu"
        )
