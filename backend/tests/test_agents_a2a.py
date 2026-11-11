"""Tests des 3 agents A2A et de l'orchestrateur (spec 6.1, D60).

Contrat : agent cards servies sous /api/agents/<nom>/.well-known/agent-card.json ;
JSON-RPC message/send fonctionne sur /api/agents/<nom>/jsonrpc ; l'orchestrateur
enchaîne les 3 agents, trace chaque délégation (kind a2a_delegate) et stream en SSE.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from investia.agents.orchestrator import run_multi_agent
from investia.llm.client import LlmResponse, ToolCall
from investia.main import create_app
from investia.market.base import MarketData

FINAL_OK = """## Thèse
AAPL vaut 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

ANALYSE = "Analyse brute : AAPL à 344.63 $ (finnhub)."


class FakeLlm:
    """LLM fake : 1er appel = tool get_quote, puis réponse finale conforme."""

    def __init__(self):
        self._first = True
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        self.calls.append({"messages": list(messages)})
        if self._first:
            self._first = False
            return LlmResponse(
                content="",
                model="gpt-6-luna",
                prompt_tokens=10,
                completion_tokens=5,
                cost_cents=0.01,
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            )
        return LlmResponse(
            content=FINAL_OK,
            model="gpt-6-luna",
            prompt_tokens=20,
            completion_tokens=50,
            cost_cents=0.02,
        )


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


class FakePortfolio:
    async def get_portfolio(self):
        return {"cash": 10_000.0, "positions": [], "total_value": 10_000.0}

    async def place_order(self, symbol, side, quantity):
        return {"ok": True}

    async def adjust_capital(self, amount, reason):
        return {"cash": 10_000.0 + amount}


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

    async def list_runs(self, limit=50):
        return []

    async def get_run(self, run_id):
        return {"run": self.runs.get(run_id), "steps": []}


@pytest.fixture
def trace_store():
    return FakeTraceStore()


@pytest.fixture
def app(monkeypatch, trace_store):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=trace_store,
    )


async def test_agent_cards_served_under_each_mount(app):
    """Chaque agent sert sa card sous /api/agents/<nom>/.well-known/..."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for name in ("analyste", "risque", "redacteur"):
            resp = await client.get(f"/api/agents/{name}/.well-known/agent-card.json")
            assert resp.status_code == 200, name
            card = resp.json()
            assert card["name"] == name
            assert card["description"]


def _message_send_body(text: str, msg_id: str = "m1") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "SendMessage",
        "params": {
            "protocolVersion": "1.0",
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": text}],
                "messageId": msg_id,
            },
        },
    }


async def test_jsonrpc_message_send_on_analyste_returns_artifact(app):
    """Le vrai protocole : POST JSON-RPC SendMessage sur l'analyste → artifact."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # le lifespan des sous-apps A2A est nécessaire (task store / handler)
        mount = next(
            r for r in app.routes if getattr(r, "path", "") == "/api/agents/analyste"
        )
        async with mount.app.router.lifespan_context(mount.app):
            resp = await client.post(
                "/api/agents/analyste/jsonrpc",
                json=_message_send_body("analyse AAPL"),
                headers={"A2A-Version": "1.0"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body or "error" not in body
    # la réponse contient un artifact avec l'analyse produite par le LLM fake
    text = json.dumps(body)
    assert "344.63" in text


async def test_orchestrator_chains_three_agents_and_traces(trace_store):
    """Flux complet (client fake) : analyste → risque → rédacteur, 3 délégations."""
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    class FakeCaller:
        """Client A2A fake : appelle directement la logique de chaque agent."""

        def __init__(self, llm, tools):
            self._llm = llm
            self._tools = tools
            self.calls: list[str] = []

        async def call(self, agent: str, text: str) -> dict[str, Any]:
            self.calls.append(agent)
            if agent == "analyste":
                return {"analysis": ANALYSE}
            if agent == "risque":
                return {"ok": True, "failures": []}
            return {"answer": FINAL_OK}

    from investia.tools import build_tools

    llm = FakeLlm()
    tools = build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    caller = FakeCaller(llm, tools)
    result = await run_multi_agent(
        "analyse AAPL",
        llm=llm,
        tools=tools,
        trace_store=trace_store,
        event_sink=sink,
        caller=caller,
    )
    assert caller.calls == ["analyste", "risque", "redacteur"]
    assert "344.63" in result.answer
    kinds = [k for k, _ in events]
    # un événement running + un ok par délégation (SSE), dernier événement = done
    ok_delegates = [
        p["agent"] for k, p in events if k == "a2a_delegate" and p["status"] == "ok"
    ]
    assert ok_delegates == ["analyste", "risque", "redacteur"]
    assert kinds[-1] == "done"
    # trace en base : un seul step a2a_delegate par agent (statut final)
    delegate_steps = [p for _, _, k, p in trace_store.steps if k == "a2a_delegate"]
    assert [p["agent"] for p in delegate_steps] == ["analyste", "risque", "redacteur"]


async def test_orchestrator_blocks_when_risque_refuses(trace_store):
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    class RefusingCaller:
        async def call(self, agent: str, text: str) -> dict[str, Any]:
            if agent == "analyste":
                return {"analysis": ANALYSE}
            if agent == "risque":
                return {"ok": False, "failures": [("format", "pas de disclaimer")]}
            return {"answer": FINAL_OK}  # ne doit pas être appelé avec ok=False

    from investia.tools import build_tools

    llm = FakeLlm()
    tools = build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    result = await run_multi_agent(
        "analyse AAPL",
        llm=llm,
        tools=tools,
        trace_store=trace_store,
        event_sink=sink,
        caller=RefusingCaller(),
    )
    assert "bloquée" in result.answer.lower() or "refus" in result.answer.lower()
    done = events[-1][1]
    assert done["status"] == "blocked"
