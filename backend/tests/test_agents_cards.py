"""Tests des agent cards enrichies de métriques (spec 20b) — TDD avant le code.

Contrat : build_agent_card(stats=...) enrichit la description de la card avec
les métriques de l'agent (runs + % succès, feedbacks 18a) ; sans stats (ou
runs=0) la card est strictement identique à 6.1/15b. La signature JWS (15b)
est appliquée après enrichissement. La route .well-known/agent-card.json peut
reconstruire la card à chaque GET via un card_factory (métriques vivantes),
l'erreur du provider est avalée (card sans métriques, jamais de 500).
"""

import httpx
import pytest
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.types import AgentCard

from investia.agents.cards import (
    DESCRIPTIONS,
    build_agent_card,
    make_card_signer,
    verify_agent_card,
)
from investia.agents.server import build_agent_subapp


def _es256_key() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_card_sans_stats_description_inchangee():
    """Zéro régression : sans stats, la description est exactement celle de 6.1."""
    card = build_agent_card("analyste", base_url="http://test")
    assert card.description == DESCRIPTIONS["analyste"]


def test_card_stats_zero_runs_description_inchangee():
    """Aucun feedback pour l'instant -> card inchangée (pas de métrique à 0)."""
    card = build_agent_card(
        "analyste", base_url="http://test", stats={"runs": 0.0, "success_rate": 0.0}
    )
    assert card.description == DESCRIPTIONS["analyste"]


def test_card_avec_stats_description_enrichie():
    card = build_agent_card(
        "risque", base_url="http://test", stats={"runs": 12.0, "success_rate": 0.92}
    )
    assert card.description.startswith(DESCRIPTIONS["risque"])
    assert "12 runs" in card.description
    assert "92%" in card.description


def test_card_signee_avec_stats_signature_valide():
    """La signature JWS couvre la card enrichie (signée après ajout des stats)."""
    key = _es256_key()
    signer = make_card_signer(key, kid="test-kid", alg="ES256")
    card = build_agent_card(
        "redacteur",
        base_url="http://test",
        signer=signer,
        stats={"runs": 5.0, "success_rate": 1.0},
    )
    assert len(card.signatures) == 1
    assert "5 runs" in card.description
    verify_agent_card(card, key)  # ne lève rien


class _NoopExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        raise NotImplementedError

    async def cancel(self, context, event_queue):
        raise NotImplementedError


async def _get_card(app) -> dict:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    return resp.json()


async def test_card_factory_reconstruit_la_card_a_chaque_get():
    """20b : la route sert la card reconstruite par card_factory à chaque GET."""
    card = build_agent_card("analyste", base_url="http://test")
    appels = 0

    async def card_factory() -> AgentCard:
        nonlocal appels
        appels += 1
        return build_agent_card(
            "analyste",
            base_url="http://test",
            stats={"runs": float(appels), "success_rate": 1.0},
        )

    app = build_agent_subapp(card, _NoopExecutor(), card_factory=card_factory)
    body1 = await _get_card(app)
    body2 = await _get_card(app)
    assert appels == 2
    assert "1 runs" in body1["description"]
    assert "2 runs" in body2["description"]


async def test_card_factory_sans_factory_sert_la_card_statique():
    """Zéro régression : sans card_factory, la card servie est la card passée."""
    card = build_agent_card("analyste", base_url="http://test")
    app = build_agent_subapp(card, _NoopExecutor())
    body = await _get_card(app)
    assert body["description"] == DESCRIPTIONS["analyste"]


async def test_card_factory_qui_leve_sert_la_card_sans_metriques():
    """Le provider de stats en panne ne casse jamais la card (erreur avalée)."""
    card = build_agent_card("analyste", base_url="http://test")

    async def card_factory() -> AgentCard:
        raise RuntimeError("DB down")

    app = build_agent_subapp(card, _NoopExecutor(), card_factory=card_factory)
    body = await _get_card(app)
    assert body["description"] == DESCRIPTIONS["analyste"]


# --- stats() du store (mapping pur + intégration pgvector) ---------------------


def test_stats_mapping_depuis_lignes():
    """20b : le mapping lignes SQL -> dict stats est pur et testable sans DB."""
    from investia.agents.router_store import stats_from_rows

    rows = [
        {"agent": "analyste", "runs": 10, "success_rate": 0.9},
        {"agent": "risque", "runs": 10, "success_rate": 1.0},
        {"agent": "redacteur", "runs": 4, "success_rate": 0.5},
    ]
    stats = stats_from_rows(rows)
    assert stats == {
        "analyste": {"runs": 10.0, "success_rate": 0.9},
        "risque": {"runs": 10.0, "success_rate": 1.0},
        "redacteur": {"runs": 4.0, "success_rate": 0.5},
    }
    assert stats_from_rows([]) == {}


@pytest.mark.integration
async def test_integration_db_agent_feedback_stats():
    """20b : stats() en pgvector réel — agrège les feedbacks par agent."""
    from investia.agents.router_store import DbAgentFeedback
    from investia.db import get_session
    from investia.memory.embeddings import FakeEmbeddingsForTests

    store = DbAgentFeedback(get_session(), FakeEmbeddingsForTests())
    await store.record("question A", ["analyste", "risque"], True)
    await store.record("question B", ["analyste", "risque"], False)
    await store.record("question C", ["analyste", "redacteur"], True)
    stats = await store.stats()
    assert stats["analyste"] == {"runs": 3.0, "success_rate": pytest.approx(2 / 3)}
    assert stats["risque"] == {"runs": 2.0, "success_rate": 0.5}
    assert stats["redacteur"] == {"runs": 1.0, "success_rate": 1.0}
