"""Tests 18a — routeur d'agents A2A : délégation dynamique pilotée par les
feedbacks passés (k-NN pondéré, même pattern que le routeur de modèles 12h),
avec fallback sur le pipeline fixe analyste → risque → rédacteur."""

import pytest

from investia.agents.router import (
    AgentNeighbor,
    FixedPipelineRouter,
    LearnedAgentRouter,
)

CANONICAL = ["analyste", "risque", "redacteur"]


class FakeAgentStore:
    def __init__(self, neighbors=None):
        self._neighbors = list(neighbors or [])
        self.recorded: list[tuple[str, list[str], bool]] = []

    async def neighbors(self, question: str, k: int = 7) -> list[AgentNeighbor]:
        return self._neighbors[:k]

    async def record(self, question: str, agents: list[str], success: bool) -> None:
        self.recorded.append((question, list(agents), success))


def n(similarity: float, agent: str, success: bool) -> AgentNeighbor:
    return AgentNeighbor(similarity=similarity, agent=agent, success=success)


async def test_fixed_pipeline_router_choisit_les_3_agents_par_defaut():
    router = FixedPipelineRouter()
    agents, source = await router.choose("n'importe quelle question")
    assert agents == CANONICAL
    assert source == "fixed"


async def test_learned_router_fallback_si_trop_peu_de_feedbacks():
    store = FakeAgentStore(neighbors=[n(0.9, "analyste", True)])
    router = LearnedAgentRouter(store)  # min_feedbacks=5 par défaut
    agents, source = await router.choose("q")
    assert source == "fixed"
    assert agents == CANONICAL


async def test_learned_router_choisit_selon_les_scores_et_garde_la_gate_risque():
    # 6 voisins : analyste et rédacteur réussissent, risque échoue mais reste
    # la gate (toujours incluse si du learned est retenu)
    neighbors = [
        n(0.95, "analyste", True),
        n(0.90, "redacteur", True),
        n(0.85, "risque", True),
        n(0.80, "analyste", True),
        n(0.75, "redacteur", True),
        n(0.70, "risque", True),
    ]
    router = LearnedAgentRouter(FakeAgentStore(neighbors), min_score=0.5)
    agents, source = await router.choose("analyse AAPL en profondeur")
    assert source == "learned"
    assert agents == CANONICAL  # tous ont score >= 0.5


async def test_learned_router_exclut_un_agent_qui_echoue_et_garde_risque():
    neighbors = [
        n(0.95, "analyste", True),
        n(0.90, "risque", False),  # score 0 -> exclu, mais gate conservée
        n(0.85, "redacteur", False),
        n(0.80, "analyste", True),
        n(0.75, "risque", False),
        n(0.70, "redacteur", False),
    ]
    router = LearnedAgentRouter(FakeAgentStore(neighbors), min_score=0.5)
    agents, source = await router.choose("prix de BTC ?")
    assert source == "learned"
    # ordre canonique, rédacteur exclu, gate risque toujours là
    assert agents == ["analyste", "risque"]


async def test_learned_router_fallback_si_aucun_agent_au_dessus_du_seuil():
    neighbors = [n(0.9, a, False) for a in CANONICAL for _ in range(2)]
    router = LearnedAgentRouter(FakeAgentStore(neighbors), min_score=0.5)
    agents, source = await router.choose("q")
    # aucun spécialiste au-dessus du seuil -> pipeline fixe complet
    assert source == "fixed"
    assert agents == CANONICAL


async def test_learned_router_record_delegue_au_store():
    store = FakeAgentStore()
    router = LearnedAgentRouter(store)
    await router.record("q", ["analyste", "risque"], True)
    assert store.recorded == [("q", ["analyste", "risque"], True)]


@pytest.mark.integration
async def test_integration_db_agent_feedback_roundtrip():
    """Roundtrip réel sur pgvector : record puis neighbors (k-NN cosinus)."""
    from investia.agents.router_store import DbAgentFeedback
    from investia.db import get_session
    from investia.memory.embeddings import FakeEmbeddingsForTests

    store = DbAgentFeedback(get_session(), FakeEmbeddingsForTests())
    await store.record("analyse AAPL ?", ["analyste", "risque"], True)
    await store.record("prix de BTC ?", ["analyste"], False)
    neighbors = await store.neighbors("analyse AAPL ?", k=2)
    assert len(neighbors) >= 1
    assert all(n.agent in {"analyste", "risque"} for n in neighbors)
    assert all(0.0 <= n.similarity <= 1.0 for n in neighbors)
