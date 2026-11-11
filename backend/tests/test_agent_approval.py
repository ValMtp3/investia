"""Tests de l'interception de simulate_order (validation humaine, spec 5.1).

Contrat : avec un ApprovalRegistry, l'appel à simulate_order émet approval_request,
loggue un step pending, attend la décision (timeout = refus), puis exécute ou non
l'ordre. Sans registry, l'outil s'exécute directement (rétrocompatible CLI/evals).
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from investia.agent import run_agent
from investia.agent.approval import ApprovalRegistry
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools


class FakeLlm:
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


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 11, 7, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


class FakePortfolioService:
    def __init__(self):
        self.orders: list[tuple[str, str, float]] = []

    async def get_portfolio(self):
        return {"cash": 10_000.0, "positions": [], "total_value": 10_000.0}

    async def place_order(self, symbol, side, quantity):
        self.orders.append((symbol, side, quantity))
        return {
            "order_id": "ord-1",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
        }


class FakeTraceStore:
    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.steps: list[tuple[str, int, str, dict]] = []
        self._next = 0

    async def start_run(self, question):
        self._next += 1
        run_id = f"00000000-0000-0000-0000-{self._next:012d}"
        self.runs[run_id] = {"question": question, "status": "running"}
        return run_id

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append((run_id, turn, kind, payload))

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.runs[run_id].update(status=status, answer=answer)


def make_response(content="", tool_calls=None, cost=0.01):
    return LlmResponse(
        content=content,
        model="gpt-6-luna",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


def order_tool_call(symbol="AAPL", side="buy", quantity=3.0):
    return [
        ToolCall(
            id="call_1",
            name="simulate_order",
            arguments={"symbol": symbol, "side": side, "quantity": quantity},
        )
    ]


FINAL_OK = """## Thèse
Ordre passé (ou refusé) — voir détail.

## Risques
volatilité.

## Confiance
70

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


async def test_approved_order_is_executed_after_approval_request():
    """Flux nominal : approval_request émis, décision approved, ordre exécuté."""
    portfolio = FakePortfolioService()
    registry = ApprovalRegistry()
    store = FakeTraceStore()
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    async def decide_later(run_id, decision):
        # attend que la boucle ouvre l'attente, puis décide
        for _ in range(100):
            if registry.has(run_id):
                break
            await asyncio.sleep(0.01)
        await registry.decide(run_id, decision)

    llm = FakeLlm(
        [
            make_response(tool_calls=order_tool_call()),
            make_response(content=FINAL_OK),
        ]
    )
    tools = build_tools(FakeMarket(), portfolio_service=portfolio)

    task = asyncio.create_task(
        run_agent(
            "achète 3 AAPL",
            llm,
            tools,
            trace_store=store,
            event_sink=sink,
            approval_registry=registry,
            approval_timeout=5.0,
        )
    )
    # récupère le run_id via le premier start, puis approuve
    for _ in range(100):
        if store.runs:
            break
        await asyncio.sleep(0.01)
    run_id = next(iter(store.runs))
    await decide_later(run_id, "approved")
    result = await task

    # l'ordre a bien été exécuté
    assert portfolio.orders == [("AAPL", "buy", 3.0)]
    # événement approval_request émis avec les bons champs
    kinds = [k for k, _ in events]
    assert "approval_request" in kinds
    req = next(p for k, p in events if k == "approval_request")
    assert req["symbol"] == "AAPL" and req["side"] == "buy" and req["quantity"] == 3.0
    assert req["run_id"] == run_id
    # un événement approval avec la décision
    approval = next(p for k, p in events if k == "approval")
    assert approval["decision"] == "approved"
    # steps tracés : approval_request pending + approval approved
    step_kinds = [(k, p) for _, _, k, p in store.steps]
    assert any(
        k == "approval_request" and p.get("status") == "pending" for k, p in step_kinds
    )
    assert any(
        k == "approval" and p.get("decision") == "approved" for k, p in step_kinds
    )
    # tool_call final ok (ordre exécuté)
    tool_event = next(p for k, p in events if k == "tool_call")
    assert tool_event["name"] == "simulate_order" and tool_event["ok"] is True
    # le LLM a reçu le résultat de l'ordre
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "ord-1" in tool_messages[0]["content"]
    assert result.turns == 2


async def test_refused_order_is_not_executed_and_model_is_told():
    portfolio = FakePortfolioService()
    registry = ApprovalRegistry()
    store = FakeTraceStore()
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    llm = FakeLlm(
        [
            make_response(tool_calls=order_tool_call(side="sell", quantity=2.0)),
            make_response(content=FINAL_OK),
        ]
    )
    tools = build_tools(FakeMarket(), portfolio_service=portfolio)

    async def refuse_later():
        for _ in range(100):
            if store.runs:
                break
            await asyncio.sleep(0.01)
        run_id = next(iter(store.runs))
        for _ in range(100):
            if registry.has(run_id):
                break
            await asyncio.sleep(0.01)
        await registry.decide(run_id, "refused")

    task = asyncio.create_task(
        run_agent(
            "vends 2 AAPL",
            llm,
            tools,
            trace_store=store,
            event_sink=sink,
            approval_registry=registry,
            approval_timeout=5.0,
        )
    )
    await refuse_later()
    result = await task

    # aucun ordre exécuté
    assert portfolio.orders == []
    # le LLM a reçu un message de refus clair
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "refusé" in tool_messages[0]["content"].lower()
    # trace : approval refused
    assert any(
        k == "approval" and p.get("decision") == "refused" for _, _, k, p in store.steps
    )
    assert result.turns == 2


async def test_timeout_means_refused():
    portfolio = FakePortfolioService()
    registry = ApprovalRegistry()
    store = FakeTraceStore()
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    llm = FakeLlm(
        [
            make_response(tool_calls=order_tool_call()),
            make_response(content=FINAL_OK),
        ]
    )
    tools = build_tools(FakeMarket(), portfolio_service=portfolio)
    result = await run_agent(
        "achète 3 AAPL",
        llm,
        tools,
        trace_store=store,
        event_sink=sink,
        approval_registry=registry,
        approval_timeout=0.2,  # timeout court pour le test
    )
    # timeout = refus : pas d'ordre
    assert portfolio.orders == []
    approval = next(p for k, p in events if k == "approval")
    assert approval["decision"] == "timeout"
    assert any(
        k == "approval" and p.get("decision") == "timeout" for _, _, k, p in store.steps
    )
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert (
        "refusé" in tool_messages[0]["content"].lower()
        or "timeout" in tool_messages[0]["content"].lower()
    )
    assert result.turns == 2


async def test_without_registry_simulate_order_runs_directly():
    """Rétrocompatible : sans registry (CLI/evals), l'outil s'exécute directement."""
    portfolio = FakePortfolioService()
    llm = FakeLlm(
        [
            make_response(tool_calls=order_tool_call()),
            make_response(content=FINAL_OK),
        ]
    )
    tools = build_tools(FakeMarket(), portfolio_service=portfolio)
    result = await run_agent("achète 3 AAPL", llm, tools)
    assert portfolio.orders == [("AAPL", "buy", 3.0)]
    assert result.turns == 2


async def test_registry_decide_unknown_run_returns_false():
    registry = ApprovalRegistry()
    assert (
        await registry.decide("00000000-0000-0000-0000-000000000099", "approved")
        is False
    )


async def test_registry_double_decision_returns_false():
    registry = ApprovalRegistry()
    registry.open("run-1")
    assert await registry.decide("run-1", "approved") is True
    assert await registry.decide("run-1", "refused") is False
    assert await registry.wait("run-1", timeout=0.1) == "approved"
