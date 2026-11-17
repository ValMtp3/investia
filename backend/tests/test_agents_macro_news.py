"""Tests 24b : agents racine macro + news (spec docs/specs/24b)."""

import asyncio
import json
from typing import Any, cast

import httpx
import pytest
from test_agents_a2a import (
    ANALYSE,
    FINAL_OK,
    FakeLlm,
    FakeMarket,
    FakePortfolio,
    FakeTraceStore,
)
from test_agents_streaming import _FakeEventQueue

from investia.agents.orchestrator import run_multi_agent
from investia.agents.plan import AGENT_SPECS, produced_fields, topological_levels
from investia.agents.router import CANONICAL_PIPELINE, AgentNeighbor, LearnedAgentRouter

# --- plan.py : macro et news sont des racines --------------------------------


def test_plan_macro_news_sont_racines():
    levels = topological_levels(["macro", "news", "analyste", "risque", "redacteur"])
    assert levels == [["macro", "news", "analyste"], ["risque"], ["redacteur"]]


def test_produced_fields_multi_champs():
    assert produced_fields("analyste") == ("analysis",)
    assert produced_fields("macro") == ("macro",)
    assert produced_fields("news") == ("news",)
    assert produced_fields("risque") == ("verdict",)
    assert produced_fields("agent-inconnu") == ("analysis",)  # fallback
    assert "macro" in AGENT_SPECS and "news" in AGENT_SPECS


# --- orchestrateur : 3 racines en parallèle, contexte multi-champs ------------


class FiveCaller:
    """Caller fake 5 agents : mesure la concurrence et garde les payloads reçus."""

    def __init__(self):
        self.calls: list[str] = []
        self.payloads: dict[str, str] = {}
        self.active = 0
        self.max_active = 0

    async def call(self, agent: str, text: str, on_event=None) -> dict[str, Any]:
        self.calls.append(agent)
        self.payloads[agent] = text
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        self.active -= 1
        if agent == "risque":
            return {"ok": True, "failures": []}
        if agent == "redacteur":
            return {"answer": FINAL_OK}
        if agent == "macro":
            return {"macro": "Hausse des taux BCE"}
        if agent == "news":
            return {"news": "AAPL +2% sur résultats"}
        return {"analysis": ANALYSE}


class FakeRouter:
    def __init__(self, agents, source="learned"):
        self._agents = list(agents)
        self._source = source

    async def choose(self, question):
        return list(self._agents), self._source

    async def record(self, question, agents, success):
        return None


async def test_trois_racines_tournent_en_parallele():
    """24b : analyste + macro + news démarrent ensemble (max_active == 3)."""
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    caller = FiveCaller()
    router = FakeRouter(["analyste", "macro", "news", "risque", "redacteur"])
    result = await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=FakeTraceStore(),
        event_sink=sink,
        caller=caller,
        router=router,
    )
    assert caller.max_active == 3
    parallel = [p for k, p in events if k == "a2a_parallel"]
    assert len(parallel) == 1
    assert parallel[0] == {
        "agents": ["analyste", "macro", "news"],
        "level": 0,
    }
    assert result.status == "ok"
    assert result.agents_used == ["analyste", "macro", "news", "risque", "redacteur"]


async def test_redacteur_recoit_analysis_macro_news_verdict():
    """24b : le payload du rédacteur contient tous les champs produits."""
    caller = FiveCaller()
    router = FakeRouter(["analyste", "macro", "news", "risque", "redacteur"])
    await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=FakeTraceStore(),
        caller=caller,
        router=router,
    )
    context = json.loads(caller.payloads["redacteur"])
    assert context["analysis"] == ANALYSE
    assert context["macro"] == "Hausse des taux BCE"
    assert context["news"] == "AAPL +2% sur résultats"
    assert context["verdict"] == {"ok": True, "failures": []}
    assert context["question"] == "analyse AAPL"


async def test_pipeline_fixe_ignore_macro_news():
    """24b zéro régression : router=None -> 3 agents seulement, jamais macro/news."""
    caller = FiveCaller()
    result = await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=FakeTraceStore(),
        caller=caller,
    )
    assert caller.calls == ["analyste", "risque", "redacteur"]
    assert result.agents_used == ["analyste", "risque", "redacteur"]


# --- router learned : ordre généralisé ----------------------------------------


class FakeStore:
    def __init__(self, neighbors):
        self._neighbors = list(neighbors)
        self.recorded: list = []

    async def record(self, question, agents, success):
        self.recorded.append((question, list(agents), success))

    async def neighbors(self, question, k):
        return self._neighbors

    async def stats(self):
        return {}


async def test_learned_router_inclut_macro_news_ordre_generalise():
    """24b : chosen = canonique d'abord, puis macro/news (ordre AGENT_SPECS)."""
    neighbors = [
        AgentNeighbor(0.9, "analyste", True),
        AgentNeighbor(0.9, "macro", True),
        AgentNeighbor(0.9, "news", True),
        AgentNeighbor(0.9, "risque", True),
        AgentNeighbor(0.8, "redacteur", False),
    ]
    router = LearnedAgentRouter(FakeStore(neighbors), min_feedbacks=5, min_score=0.5)
    chosen, source = await router.choose("contexte macro ?")
    assert source == "learned"
    assert chosen == ["analyste", "risque", "macro", "news"]  # redacteur score < 0.5


async def test_learned_router_fallback_sans_feedbacks():
    router = LearnedAgentRouter(FakeStore([]), min_feedbacks=5)
    chosen, source = await router.choose("q")
    assert source == "fixed"
    assert chosen == CANONICAL_PIPELINE  # 3 agents, pas macro/news


# --- cards + montage main.py ---------------------------------------------------


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    from investia.main import create_app

    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=FakeTraceStore(),
    )


async def test_cards_macro_et_news_servies(app):
    """24b : les 5 agents sont montés, cards macro/news en 200."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for name in ("macro", "news"):
            resp = await client.get(f"/api/agents/{name}/.well-known/agent-card.json")
            assert resp.status_code == 200, name
            assert resp.json()["name"] == name


# --- executors : artifacts macro/news + prompt du rédacteur -------------------


def _context(text: str):
    from a2a.server.agent_execution.context import RequestContext
    from a2a.types import Message, Part, SendMessageRequest

    return RequestContext(
        call_context=cast(Any, None),
        request=SendMessageRequest(
            message=Message(role="ROLE_USER", parts=[Part(text=text)], message_id="m1")
        ),
        task_id="t1",
        context_id="c1",
    )


async def test_macro_executor_produit_artifact_macro():
    from investia.agents.executors import MacroExecutor
    from investia.tools import build_tools

    llm = FakeLlm()
    executor = MacroExecutor(
        llm, build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    )
    queue = _FakeEventQueue()
    await executor.execute(_context("contexte macro ?"), cast(Any, queue))
    finals = [
        ev.artifact
        for ev in queue.events
        if getattr(ev, "artifact", None) and ev.artifact.name != "step"
    ]
    assert len(finals) == 1 and finals[0].name == "macro"
    assert "macro" in json.loads(finals[0].parts[0].text)


async def test_news_executor_produit_artifact_news():
    from investia.agents.executors import NewsExecutor
    from investia.tools import build_tools

    executor = NewsExecutor(
        FakeLlm(), build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    )
    queue = _FakeEventQueue()
    await executor.execute(_context("actualités AAPL ?"), cast(Any, queue))
    finals = [
        ev.artifact
        for ev in queue.events
        if getattr(ev, "artifact", None) and ev.artifact.name != "step"
    ]
    assert len(finals) == 1 and finals[0].name == "news"
    assert "news" in json.loads(finals[0].parts[0].text)


async def test_redacteur_prompt_cite_macro_et_news_quand_presents():
    from investia.agents.executors import RedacteurExecutor
    from investia.tools import build_tools

    llm = FakeLlm()
    executor = RedacteurExecutor(
        llm, build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    )
    payload = json.dumps(
        {
            "analysis": "analyse AAPL",
            "macro": "Hausse des taux BCE",
            "news": "AAPL +2%",
            "verdict": {"ok": True},
        }
    )
    queue = _FakeEventQueue()
    await executor.execute(_context(payload), cast(Any, queue))
    prompt = json.dumps(llm.calls[0]["messages"])
    assert "Hausse des taux BCE" in prompt
    assert "AAPL +2%" in prompt


async def test_redacteur_prompt_identique_sans_macro_news():
    """24b zéro régression : sans macro/news, pas de section dans le prompt."""
    from investia.agents.executors import RedacteurExecutor
    from investia.tools import build_tools

    llm = FakeLlm()
    executor = RedacteurExecutor(
        llm, build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    )
    payload = json.dumps({"analysis": "analyse AAPL", "verdict": {"ok": True}})
    queue = _FakeEventQueue()
    await executor.execute(_context(payload), cast(Any, queue))
    prompt = json.dumps(llm.calls[0]["messages"])
    assert "Macro" not in prompt
    assert "Actualités" not in prompt
