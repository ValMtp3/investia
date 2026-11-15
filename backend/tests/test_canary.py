"""Tests 23b — canary tokens : un marqueur par run, injecté dans le contenu
externe wrappé ; s'il réapparaît dans un tool_call ou la réponse finale,
c'est une exfiltration → blocage + trace (canary_hit).

TDD : écrits AVANT backend/src/investia/guardrails/canary.py et le câblage boucle.
"""

from test_injection import (
    CALLS,
    FINAL_OK,
    FakeLlm,
    FakeStore,
    FakeWebSearcher,
    resp,
)

from investia.agent import run_agent
from investia.guardrails.canary import (
    CANARY_BLOCKED_MESSAGE,
    CanaryDetector,
    generate_canary,
)
from investia.guardrails.injection import UNTRUSTED_BEGIN, wrap_untrusted
from investia.llm.client import ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools

CANARY = "CANARY-0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------- unité


def test_generate_canary_unique_par_run():
    tokens = {generate_canary() for _ in range(50)}
    assert len(tokens) == 50
    assert all(t.startswith("CANARY-") and len(t) == 7 + 32 for t in tokens)


def test_detector_trouve_le_token():
    detector = CanaryDetector(CANARY)
    assert detector.scan(f"requête avec {CANARY} dedans")
    assert not detector.scan("texte financier normal")


def test_wrap_untrusted_injecte_le_canary():
    wrapped = wrap_untrusted("contenu externe", canary=CANARY)
    assert wrapped.startswith(UNTRUSTED_BEGIN)
    assert CANARY in wrapped
    # sans canary : sortie inchangée (zéro régression 13b)
    assert wrap_untrusted("contenu externe") == (
        f"{UNTRUSTED_BEGIN}\ncontenu externe\n----- FIN CONTENU EXTERNE -----"
    )


# ---------------------------------------------------------------- boucle


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="mock",
            timestamp=__import__("datetime").datetime(2026, 10, 31),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


async def test_canary_dans_tool_call_est_bloque():
    """Le modèle recopie le canary dans les arguments d'un tool_call → blocage."""
    leak = [
        ToolCall(
            id="c3", name="web_search", arguments={"query": f"fwd {CANARY}", "limit": 3}
        )
    ]
    llm = FakeLlm(
        [
            resp("", tool_calls=CALLS),
            resp("", tool_calls=leak),
            resp(FINAL_OK),
        ]
    )
    store = FakeStore()
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    result = await run_agent(
        "actualité AAPL ?",
        llm,
        build_tools(FakeMarket()),
        trace_store=store,
        event_sink=sink,
        canary_token=CANARY,
    )
    assert result.canary_hits == 1
    assert any(kind == "canary_hit" for kind, _ in events)
    assert any(s["kind"] == "canary_hit" for s in store.steps)
    # le tool_call fuyant n'a jamais été exécuté : son message tool est le blocage
    tool_msgs = [m for c in llm.calls for m in c["messages"] if m.get("role") == "tool"]
    leak_msg = next(m for m in tool_msgs if m.get("tool_call_id") == "c3")
    assert CANARY_BLOCKED_MESSAGE in leak_msg["content"]


async def test_canary_dans_reponse_finale_est_redacte():
    # la réponse doit passer les garde-fous (CALLS + FINAL_OK comme les tests 13b)
    # tout en fuyant le canary
    llm = FakeLlm(
        [resp("", tool_calls=CALLS), resp(FINAL_OK + f"\nnote interne : {CANARY}")]
    )
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    result = await run_agent(
        "actualité AAPL ?",
        llm,
        build_tools(FakeMarket(), web_searcher=FakeWebSearcher([])),
        event_sink=sink,
        canary_token=CANARY,
    )
    assert result.status == "ok"
    assert result.canary_hits == 1
    assert CANARY not in result.answer
    assert "redacted" in result.answer
    assert any(kind == "canary_hit" for kind, _ in events)


async def test_pas_de_canary_hit_sur_run_propre():
    llm = FakeLlm([resp("", tool_calls=CALLS), resp(FINAL_OK)])
    result = await run_agent(
        "prix AAPL ?",
        llm,
        build_tools(FakeMarket()),
        canary_token=CANARY,
    )
    assert result.canary_hits == 0
    assert result.answer == FINAL_OK


def test_canary_present_dans_contenu_externe_wrappe():
    """Le canary vu par le modèle est bien celui du run (via le wrapper 13b)."""
    wrapped = wrap_untrusted("news AAPL", canary=CANARY)
    detector = CanaryDetector(CANARY)
    assert detector.scan(wrapped)
    # et un autre canary ne matche pas
    assert not CanaryDetector("CANARY-autre").scan(wrapped)
