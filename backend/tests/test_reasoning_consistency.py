"""Tests TDD de la brique 12c : self-consistency (vote + k runs parallèles + evals)."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from investia.agent import run_agent
from investia.agent.reasoning import extract_confidence, normalize_answer, vote
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools


# --- Task 1 : fonctions pures de vote ---


def test_normalize_answer_casse_et_espaces():
    assert normalize_answer("  Réponse\n A  ") == "réponse a"


def test_extract_confidence_present():
    assert extract_confidence("## Confiance\n80\n") == 80
    assert extract_confidence("## confiance : 65") == 65


def test_extract_confidence_absent():
    assert extract_confidence("pas de section") == 0


def test_vote_majoritaire_gagne():
    index, consensus = vote(["Réponse A", "réponse a ", "Réponse B"])
    assert index == 0
    assert consensus == pytest.approx(2 / 3)


def test_vote_ex_aequo_confiance_la_plus_haute_gagne():
    a = "## Thèse\nA\n\n## Confiance\n50"
    b = "## Thèse\nB\n\n## Confiance\n90"
    c = "## Thèse\nC\n\n## Confiance\n70"
    index, consensus = vote([a, b, c])
    assert index == 1
    assert consensus == pytest.approx(1 / 3)


def test_vote_ex_aequo_sans_confiance_premier_gagne():
    index, consensus = vote(["A", "B", "C"])
    assert index == 0
    assert consensus == pytest.approx(1 / 3)


def test_vote_un_seul_et_vide():
    assert vote(["x"]) == (0, 1.0)
    assert vote([]) == (0, 1.0)  # garde-fou, jamais appelé en pratique


# --- Task 2 : wrapper run_agent(consistency_k, llm_factory) ---


class FakeLlm:
    def __init__(self, responses: list[LlmResponse]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        self.calls.append({"model": model_key, "messages": list(messages), "tools": tools})
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
        self._n = 0

    async def start_run(self, question):
        self._n += 1
        return f"run-{self._n}"

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append((run_id, turn, kind, payload))

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.finished.append({"run_id": run_id, "status": status, "cost_cents": cost_cents})


FINAL_A = """## Thèse
Le prix de AAPL est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

FINAL_B = """## Thèse
AAPL s'échange à 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
70

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


def quote_call():
    return [ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})]


def llm_with_final(content):
    return FakeLlm([make_response(tool_calls=quote_call()), make_response(content=content)])


async def test_k1_comportement_identique():
    llm = llm_with_final(FINAL_A)
    events = []

    async def sink(kind, payload):
        events.append(kind)

    store = FakeTraceStore()
    result = await run_agent(
        "prix de AAPL ?", llm, build_tools(FakeMarket()), trace_store=store, event_sink=sink
    )
    assert result.consensus == 1.0
    assert result.answers == []
    assert result.run_id == "run-1"
    assert len(llm.calls) == 2
    assert "start" in events and "answer" in events and "done" in events
    assert "consensus" not in events


async def test_k3_vote_majoritaire_avec_factory():
    factories = []

    def factory(i):
        factories.append(i)
        return [llm_with_final(FINAL_A), llm_with_final(FINAL_A), llm_with_final(FINAL_B)][i]

    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    store = FakeTraceStore()
    result = await run_agent(
        "prix de AAPL ?",
        FakeLlm([]),
        build_tools(FakeMarket()),
        consistency_k=3,
        llm_factory=factory,
        trace_store=store,
        event_sink=sink,
    )
    assert factories == [0, 1, 2]
    assert result.consensus == pytest.approx(2 / 3)
    assert result.answer == FINAL_A
    assert len(result.answers) == 3
    consensus_events = [p for k, p in events if k == "consensus"]
    assert len(consensus_events) == 1
    assert consensus_events[0]["winner"] == 0
    assert consensus_events[0]["k"] == 3
    assert any(s[2] == "consensus" for s in store.steps)
    # coût total = somme des 3 sous-runs (2 appels x 0.01 chacun)
    assert result.total_cost_cents == pytest.approx(0.06)
    # chaque sous-run a tracé son propre run en base
    assert len(store.finished) == 3


async def test_k3_sans_factory_meme_llm_partage():
    llm = FakeLlm(
        [make_response(tool_calls=quote_call()), make_response(content=FINAL_A)] * 3
    )
    result = await run_agent(
        "prix de AAPL ?", llm, build_tools(FakeMarket()), consistency_k=3
    )
    assert len(llm.calls) == 6  # 3 runs x 2 appels
    assert result.consensus == 1.0  # toutes les réponses identiques


async def test_k_invalide_rejete():
    llm = llm_with_final(FINAL_A)
    with pytest.raises(ValueError, match="consistency_k"):
        await run_agent(
            "prix ?", llm, build_tools(FakeMarket()), consistency_k=0
        )


async def test_k3_avec_approval_registry_rejete():
    llm = llm_with_final(FINAL_A)
    with pytest.raises(ValueError, match="approval"):
        await run_agent(
            "prix ?",
            llm,
            build_tools(FakeMarket()),
            consistency_k=3,
            approval_registry=object(),
        )
