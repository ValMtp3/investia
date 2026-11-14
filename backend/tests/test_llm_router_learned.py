"""Tests TDD du routeur appris (étape 12h) — store fake en mémoire, zéro DB."""

import re

import pytest

from investia.llm.router import LearnedRouter, Neighbor


class FakeStore:
    def __init__(self, neighbors=None):
        self._neighbors = list(neighbors or [])
        self.recorded: list[tuple[str, str, bool]] = []

    async def neighbors(self, question: str, k: int = 7) -> list[Neighbor]:
        return self._neighbors[:k]

    async def record(self, question: str, model: str, success: bool) -> None:
        self.recorded.append((question, model, success))


def n(similarity: float, model: str, success: bool) -> Neighbor:
    return Neighbor(similarity=similarity, model=model, success=success)


async def test_knn_choisit_le_modele_qui_a_reussi():
    store = FakeStore([n(0.9, "small", True)] * 6)
    router = LearnedRouter(store)
    model, source = await router.choose("question test")
    assert model == "small"
    assert source == "learned"


async def test_fallback_regles_si_moins_de_5_feedbacks():
    store = FakeStore([n(0.9, "small", True)] * 4)
    router = LearnedRouter(store)
    model, source = await router.choose("analyse approfondie de la stratégie")
    assert source == "rules"
    assert model == "large"  # règle D44 : mot-clé « analyse » -> large


async def test_fallback_regles_si_ecart_trop_faible():
    store = FakeStore([n(0.9, "small", True), n(0.9, "large", True)] * 3)
    router = LearnedRouter(store)
    _model, source = await router.choose("question neutre sans mot-clé")
    assert source == "rules"


async def test_ponderation_par_similarite():
    # small est le plus proche mais a échoué ; large est plus lointain mais a réussi
    # -> large gagne : la similarité pondère, ce n'est pas un vote brut
    store = FakeStore([n(0.95, "small", False)] * 3 + [n(0.5, "large", True)] * 3)
    router = LearnedRouter(store)
    model, source = await router.choose("q")
    assert model == "large"
    assert source == "learned"


async def test_scores_ex_aequo_tombent_sur_les_regles():
    # que des échecs côté small -> score small = 0.0 = score large (absent) -> écart 0
    store = FakeStore([n(0.9, "small", False)] * 6)
    router = LearnedRouter(store)
    _model, source = await router.choose("q")
    assert source == "rules"


async def test_record_delegue_au_store():
    store = FakeStore()
    router = LearnedRouter(store)
    await router.record("q", "small", True)
    assert store.recorded == [("q", "small", True)]


async def test_k_parametre_limite_les_voisins():
    store = FakeStore([n(0.9, "small", True)] * 10)
    router = LearnedRouter(store, k=7)
    model, source = await router.choose("q")
    assert len(store._neighbors[:7]) == 7
    assert (model, source) == ("small", "learned")


# --- Tâche 2 : migration 0008 + DbRouterFeedback ---


def _extract(pattern: str, content: str) -> str:
    match = re.search(pattern, content)
    assert match is not None, f"pattern {pattern!r} introuvable"
    return match.group(1)


def test_migration_0008_chainee_sur_0007():
    """La migration router_feedback doit suivre 0007_semantic_cache."""
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    content = (versions / "0008_router_feedback.py").read_text(encoding="utf-8")
    revision = _extract(r'revision = "([^"]+)"', content)
    down = _extract(r'down_revision = "([^"]+)"', content)
    prev = (versions / "0007_semantic_cache.py").read_text(encoding="utf-8")
    prev_revision = _extract(r'revision = "([^"]+)"', prev)
    assert revision == "0008_router_feedback"
    assert down == prev_revision
    assert "router_feedback" in content
    assert "hnsw" in content


@pytest.mark.integration
async def test_integration_db_router_feedback_roundtrip():
    """Roundtrip réel sur pgvector : record puis neighbors (k-NN cosinus)."""
    from investia.db import get_session
    from investia.llm.router_store import DbRouterFeedback
    from investia.memory.embeddings import FakeEmbeddingsForTests

    store = DbRouterFeedback(get_session(), FakeEmbeddingsForTests())
    await store.record("prix de AAPL ?", "small", True)
    await store.record("analyse de stratégie long terme ?", "large", True)
    neighbors = await store.neighbors("prix de AAPL ?", k=2)
    assert len(neighbors) >= 1
    assert neighbors[0].model == "small"
    assert neighbors[0].success is True
    assert 0.0 <= neighbors[0].similarity <= 1.0


# --- 17f : règle « préserver le cache » — un seul modèle par run ---------------

from dataclasses import replace  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from test_agent_loop import (  # noqa: E402
    FINAL_WITH_PRICE,
    FakeLlm,
    FakeMarket,
    make_response,
    quote_tool_call,
)
from test_sse import FakeTraceStore  # noqa: E402

from investia.agent import run_agent  # noqa: E402
from investia.market.base import MarketData  # noqa: E402
from investia.tools import build_tools  # noqa: E402


class FlippingRouter:
    """Routeur factice qui changerait de modèle à chaque appel (anti-cache)."""

    def __init__(self) -> None:
        self.calls = 0

    async def choose(self, question: str):
        self.calls += 1
        return ("small" if self.calls == 1 else "large"), "learned"

    async def record(self, question: str, model: str, success: bool) -> None:
        return None


async def test_run_agent_sticky_model_preserves_prompt_cache():
    # 17f : le modèle est résolu UNE fois par run ; tous les appels LLM
    # (boucle, plan, réflexion, compaction) l'utilisent, même si le routeur
    # changerait d'avis entre-temps (sinon le cache prompt saute).
    quote = MarketData(
        value=344.63,
        currency="USD",
        source="finnhub",
        timestamp=datetime(2026, 10, 31, tzinfo=UTC),
    )
    llm = FakeLlm(
        [
            replace(
                make_response(content="je cherche", tool_calls=quote_tool_call()),
                cached_tokens=42,
            ),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    router = FlippingRouter()
    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket(quote=quote)),
        trace_store=FakeTraceStore(),
        event_sink=sink,
        router=router,
    )
    assert router.calls == 1  # résolu une seule fois pour tout le run
    assert {c["model"] for c in llm.calls} == {"small"}  # aucun switch mid-run
    assert result.router_source == "learned"
    assert result.cached_tokens == 42  # tokens cachés exposés dans le résultat
    done = next(p for k, p in events if k == "done")
    assert done["model"] == "small"
    assert done["router_source"] == "learned"
    assert done["cached_tokens"] == 42
