"""Tests 24a : subagents A2A async par défaut (spec docs/specs/24a).

Contrat : l'orchestrateur exécute les agents par niveaux topologiques
(`agents/plan.py`) — les agents indépendants d'un même niveau tournent en
parallèle (asyncio.gather), le pipeline canonique (chaîne linéaire) reste
strictement identique (zéro régression, aucun event a2a_parallel).
"""

import asyncio
from typing import Any

import pytest

from investia.agents.orchestrator import run_multi_agent
from investia.agents.plan import AGENT_SPECS, AgentSpec, topological_levels

ANALYSE = "Analyse brute : AAPL à 344.63 $ (finnhub)."
FINAL_OK = "Réponse finale structurée. Simulation — pas un conseil."


# --- plan.py : niveaux topologiques -------------------------------------------


def test_topological_levels_canonical_pipeline_is_chain():
    """Pipeline canonique = 3 niveaux de 1 (aucun parallélisme possible)."""
    levels = topological_levels(["analyste", "risque", "redacteur"])
    assert levels == [["analyste"], ["risque"], ["redacteur"]]


def test_topological_levels_parallel_roots_share_level_zero():
    """Deux agents racine (sans dépendance) sont au même niveau 0."""
    specs = {**AGENT_SPECS, "macro": AgentSpec("macro", (), ("analysis",))}
    levels = topological_levels(
        ["redacteur", "analyste", "macro", "risque"], specs=specs
    )
    assert levels == [["analyste", "macro"], ["risque"], ["redacteur"]]


def test_topological_levels_unknown_agent_is_root():
    """Un agent inconnu du registre est traité comme racine (requires vide)."""
    levels = topological_levels(["nouvel-agent", "analyste", "risque"])
    assert levels[0] == ["nouvel-agent", "analyste"]
    assert levels[1] == ["risque"]


def test_topological_levels_cycle_raises_value_error():
    """Un agent qui requiert un champ qu'il produit lui-même = cycle -> ValueError."""
    specs = {"a": AgentSpec("a", requires=("a",), produces=("a",))}
    with pytest.raises(ValueError, match="cycle"):
        topological_levels(["a"], specs=specs)


# --- orchestrateur : exécution parallèle --------------------------------------


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


class ConcurrentCaller:
    """Enregistre la concurrence réelle : max_active agents simultanés."""

    def __init__(self, agents_ok=("analyste", "macro")):
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self._agents_ok = set(agents_ok)

    async def call(self, agent: str, text: str, on_event=None) -> dict[str, Any]:
        self.calls.append(agent)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)  # simule une latence réseau/LLM
        self.active -= 1
        if agent == "risque":
            return {"ok": True, "failures": []}
        if agent not in self._agents_ok:
            return {"answer": FINAL_OK}
        return {"analysis": ANALYSE}


class FakeRouter:
    def __init__(self, agents, source="learned"):
        self._agents = list(agents)
        self._source = source
        self.recorded: list[tuple[str, list[str], bool]] = []

    async def choose(self, question: str):
        return list(self._agents), self._source

    async def record(self, question: str, agents: list[str], success: bool) -> None:
        self.recorded.append((question, list(agents), success))


async def test_parallel_roots_run_concurrently_and_emit_a2a_parallel():
    """24a : 2 racines démarrent ensemble (max_active == 2) + event a2a_parallel."""
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    trace = FakeTraceStore()
    caller = ConcurrentCaller()
    router = FakeRouter(["analyste", "macro", "redacteur"])
    result = await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=trace,
        event_sink=sink,
        caller=caller,
        router=router,
    )
    assert caller.max_active == 2  # les 2 racines ont tourné en même temps
    parallel = [p for k, p in events if k == "a2a_parallel"]
    assert len(parallel) == 1
    assert sorted(parallel[0]["agents"]) == ["analyste", "macro"]
    assert parallel[0]["level"] == 0
    # les délégations portent leur niveau
    delegates = [p for k, p in events if k == "a2a_delegate" and p["status"] == "ok"]
    levels = {p["agent"]: p["level"] for p in delegates}
    # risque n'est pas sélectionné : "verdict" est hors sélection, le rédacteur
    # n'attend que "analysis" (niveau 1)
    assert levels == {"analyste": 0, "macro": 0, "redacteur": 1}
    # le rédacteur a attendu les 2 analyses (niveau 2) et répond
    assert result.status == "ok"
    assert result.answer == FINAL_OK
    assert result.agents_used == ["analyste", "macro", "redacteur"]


async def test_canonical_pipeline_emits_no_parallel_event():
    """24a zéro régression : pipeline fixe = aucun a2a_parallel, ordre inchangé."""
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    trace = FakeTraceStore()
    caller = ConcurrentCaller(agents_ok=("analyste",))
    result = await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=trace,
        event_sink=sink,
        caller=caller,
    )
    assert caller.max_active == 1  # chaîne linéaire = séquentiel
    assert "a2a_parallel" not in [k for k, _ in events]
    ok_delegates = [
        p["agent"] for k, p in events if k == "a2a_delegate" and p["status"] == "ok"
    ]
    assert ok_delegates == ["analyste", "risque", "redacteur"]
    assert result.status == "ok"


async def test_parallel_false_forces_sequential_even_with_two_roots():
    """24a opt-out : parallel=False -> max_active == 1, pas d'event a2a_parallel."""
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    caller = ConcurrentCaller()
    router = FakeRouter(["analyste", "macro", "redacteur"])
    result = await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=FakeTraceStore(),
        event_sink=sink,
        caller=caller,
        router=router,
        parallel=False,
    )
    assert caller.max_active == 1
    assert "a2a_parallel" not in [k for k, _ in events]
    assert result.status == "ok"


async def test_parallel_level_failure_waits_for_level_then_raises():
    """24a politique d'erreur : on attend tout le niveau, puis RuntimeError."""

    class OneFailsCaller:
        def __init__(self):
            self.finished: list[str] = []

        async def call(self, agent: str, text: str, on_event=None) -> dict[str, Any]:
            if agent == "bad":
                raise ConnectionError("agent down")
            await asyncio.sleep(0.05)
            self.finished.append(agent)
            return {"analysis": ANALYSE}

    caller = OneFailsCaller()
    router = FakeRouter(["slow", "bad", "redacteur"])
    with pytest.raises(RuntimeError, match="bad"):
        await run_multi_agent(
            "q",
            llm=None,
            tools={},
            trace_store=FakeTraceStore(),
            caller=caller,
            router=router,
        )
    # le voisin du même niveau a bien terminé avant l'échec du run
    assert caller.finished == ["slow"]


async def test_router_order_does_not_break_topology():
    """24a : le router renvoie un ordre quelconque, l'orchestrateur topologie-sorte."""
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    caller = ConcurrentCaller(agents_ok=("analyste",))
    router = FakeRouter(["redacteur", "risque", "analyste"])  # ordre inversé
    result = await run_multi_agent(
        "analyse AAPL",
        llm=None,
        tools={},
        trace_store=FakeTraceStore(),
        event_sink=sink,
        caller=caller,
        router=router,
    )
    assert caller.calls == ["analyste", "risque", "redacteur"]
    assert result.status == "ok"
