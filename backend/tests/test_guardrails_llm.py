"""Tests TDD de la brique 12d : garde-fous LLM en renfort (elephant-1 + logprobs)."""

from typing import Any

import pytest

from investia.guardrails.llm_check import (
    MIN_CONFIDENCE,
    NON_BLOCK_THRESHOLD,
    UNSAFE_BLOCK_THRESHOLD,
    check_safety_llm,
    check_safety_logprobs,
)
from investia.llm.client import LlmResponse
from investia.llm.decisions import DecisionAnswer


def decision(value, probabilities, confidence):
    async def decide(state, questions):
        return {
            "safety": DecisionAnswer(
                value=value, probabilities=probabilities, confidence=confidence
            )
        }

    return decide


# --- check_safety_llm (elephant-1) ---


async def test_safety_llm_bloque_si_unsafe_confiant():
    result = await check_safety_llm(
        "ça va monter", decision("unsafe", {"unsafe": 0.9, "safe": 0.1}, 0.95)
    )
    assert result.ok is False
    assert "unsafe=0.90" in result.detail


async def test_safety_llm_passe_si_confiance_basse():
    result = await check_safety_llm(
        "ça va monter", decision("unsafe", {"unsafe": 0.9, "safe": 0.1}, 0.3)
    )
    assert result.ok is True
    assert f"confiance={0.3:.2f}" in result.detail


async def test_safety_llm_passe_si_safe():
    result = await check_safety_llm(
        "analyse neutre", decision("safe", {"safe": 0.95, "unsafe": 0.05}, 0.9)
    )
    assert result.ok is True


async def test_safety_llm_erreur_indisponible_ne_bloque_pas():
    async def decide_ko(state, questions):
        raise RuntimeError("gateway down")

    result = await check_safety_llm("réponse", decide_ko)
    assert result.ok is True
    assert "indisponible" in result.detail


async def test_safety_llm_sans_reponse_indisponible():
    async def decide_vide(state, questions):
        return {}

    result = await check_safety_llm("réponse", decide_vide)
    assert result.ok is True
    assert "indisponible" in result.detail


# --- check_safety_logprobs (LLM-as-Jev) ---


class LogprobsLlm:
    """LLM fake qui rend first_token_logprobs quand on demande logprobs=True."""

    def __init__(self, logprobs: dict[str, float] | None):
        self._logprobs = logprobs
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        self.calls.append(
            {
                "model": model_key,
                "messages": list(messages),
                "tools": tools,
                "logprobs": logprobs,
                "temperature": temperature,
            }
        )
        return LlmResponse(
            content="Non" if self._logprobs else "Oui",
            model="mock",
            prompt_tokens=10,
            completion_tokens=1,
            cost_cents=0.01,
            first_token_logprobs=self._logprobs if logprobs else None,
        )


async def test_safety_logprobs_bloque_si_non_probable():
    llm = LogprobsLlm({"Non": 0.98, "Oui": 0.02})
    result = await check_safety_logprobs("ça va monter", llm, "small")
    assert result.ok is False
    assert "P(non)=0.98" in result.detail
    assert llm.calls[0]["logprobs"] is True
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["temperature"] == 0.0


async def test_safety_logprobs_passe_si_oui_probable():
    llm = LogprobsLlm({"Oui": 0.9, "Non": 0.1})
    result = await check_safety_logprobs("analyse neutre", llm, "small")
    assert result.ok is True


async def test_safety_logprobs_sans_logprobs_indisponible():
    llm = LogprobsLlm(None)
    result = await check_safety_logprobs("réponse", llm, "small")
    assert result.ok is True
    assert "indisponible" in result.detail


def test_seuils_sont_coherents():
    assert UNSAFE_BLOCK_THRESHOLD == 0.7
    assert MIN_CONFIDENCE == 0.6
    assert NON_BLOCK_THRESHOLD == 0.7


# --- Task 3 : boucle run_agent(decision_client / logprobs_guardrail) ---

from datetime import UTC, datetime

from investia.agent import run_agent
from investia.llm.client import ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools


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


class FakeLlm:
    def __init__(self, responses, logprobs=None):
        self._responses = list(responses)
        self._logprobs = logprobs
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        self.calls.append({"logprobs": logprobs, "tools": tools})
        if logprobs and self._logprobs is not None:
            return LlmResponse(
                content="Non",
                model="mock",
                prompt_tokens=10,
                completion_tokens=1,
                cost_cents=0.01,
                first_token_logprobs=self._logprobs,
            )
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class FakeDecisionClient:
    def __init__(self, value, probabilities, confidence):
        self._answer = DecisionAnswer(
            value=value, probabilities=probabilities, confidence=confidence
        )

    async def decide(self, state, questions):
        return {"safety": self._answer}


class FakeTraceStore:
    def __init__(self):
        self.steps = []
        self.finished = []

    async def start_run(self, question):
        return "run-1"

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append((kind, payload))

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.finished.append({"status": status})


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


def make_response(content="", tool_calls=None, cost=0.01):
    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


def quote_call():
    return [ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})]


def llm_ok(logprobs=None):
    return FakeLlm([make_response(tool_calls=quote_call()), make_response(content=FINAL_OK)], logprobs=logprobs)


async def test_boucle_safety_llm_present_avec_decision_client():
    store = FakeTraceStore()
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    client = FakeDecisionClient("safe", {"safe": 0.95, "unsafe": 0.05}, 0.9)
    result = await run_agent(
        "prix de AAPL ?",
        llm_ok(),
        build_tools(FakeMarket()),
        decision_client=client,
        trace_store=store,
        event_sink=sink,
    )
    checks = {g.check: g.ok for g in result.guardrails}
    assert checks.get("safety_llm") is True
    assert any(k == "guardrail" and p.get("check") == "safety_llm" for k, p in events)
    assert any(kind == "guardrail" and payload.get("check") == "safety_llm" for kind, payload in store.steps)
    assert store.finished[0]["status"] == "ok"


async def test_boucle_safety_llm_bloque_si_unsafe():
    store = FakeTraceStore()
    client = FakeDecisionClient("unsafe", {"unsafe": 0.9, "safe": 0.1}, 0.95)
    result = await run_agent(
        "prix de AAPL ?",
        llm_ok(),
        build_tools(FakeMarket()),
        decision_client=client,
        trace_store=store,
    )
    checks = {g.check: g.ok for g in result.guardrails}
    assert checks.get("safety_llm") is False
    assert store.finished[0]["status"] == "blocked"
    assert "bloquée" in result.answer


async def test_boucle_safety_logprobs_avec_flag():
    store = FakeTraceStore()
    llm = llm_ok(logprobs={"Non": 0.98, "Oui": 0.02})
    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        logprobs_guardrail=True,
        trace_store=store,
    )
    checks = {g.check: g.ok for g in result.guardrails}
    assert checks.get("safety_logprobs") is False
    assert store.finished[0]["status"] == "blocked"
    assert any(c["logprobs"] is True for c in llm.calls)


async def test_sans_rien_aucun_check_llm():
    llm = llm_ok()
    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    checks = {g.check for g in result.guardrails}
    assert "safety_llm" not in checks
    assert "safety_logprobs" not in checks
    assert all(c["logprobs"] is False for c in llm.calls)


async def test_k3_transmet_logprobs_guardrail_aux_sous_runs():
    def factory(i):
        return llm_ok(logprobs={"Oui": 0.9, "Non": 0.1})

    result = await run_agent(
        "prix de AAPL ?",
        FakeLlm([]),
        build_tools(FakeMarket()),
        consistency_k=3,
        llm_factory=factory,
        logprobs_guardrail=True,
    )
    checks = {g.check: g.ok for g in result.guardrails}
    assert checks.get("safety_logprobs") is True
    assert result.consensus == 1.0
