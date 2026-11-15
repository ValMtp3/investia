"""Tests d'intégration mémoire : vraie table pgvector (conteneur Docker, port 5432)."""

import math
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from investia.db import get_session
from investia.memory.embeddings import FakeEmbeddingsForTests
from investia.memory.store import DbMemoryStore
from investia.redaction import REDACTED

pytestmark = pytest.mark.integration

# Ordre : URL pgvector dédiée, puis la base de test commune (celle de la CI, comme les
# autres tests d'intégration), puis la base locale Docker. Sans le 2e choix, la CI
# retombait sur le mot de passe local et échouait (« password authentication failed »).
TEST_PG_URL = (
    os.environ.get("TEST_PGVECTOR_URL")
    or os.environ.get("TEST_DATABASE_URL")
    or "postgresql+asyncpg://investia:localtest123@127.0.0.1:5432/investia_test"
)
BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_PG_URL)
    import investia.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    yield DbMemoryStore(get_session(), embeddings=FakeEmbeddingsForTests())
    db_module._engine = None
    db_module._session_factory = None


@pytest.mark.skipif(
    not os.environ.get("TEST_PGVECTOR_URL", "1"), reason="pgvector requis"
)
def test_alembic_upgrade_head_creates_memories_table():
    assert TEST_PG_URL is not None
    env = {**os.environ, "DATABASE_URL": TEST_PG_URL}
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_save_recall_roundtrip_on_real_pgvector(store):
    # embeddings de test = hash déterministe : on rappelle avec le texte exact
    # (le vrai test sémantique passe en live avec de vrais embeddings OpenRouter)
    await store.save("profil de risque prudent", None)
    await store.save("il déteste les cryptos", None)
    await store.save("horizon investissement 10 ans", None)

    results = await store.recall("profil de risque prudent", k=1)
    assert len(results) == 1
    assert "prudent" in results[0]["content"]
    assert results[0]["score"] == pytest.approx(1.0)


async def test_recall_returns_top_k_ordered(store):
    results = await store.recall("horizon long terme", k=3)
    assert len(results) == 3
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


async def test_temporal_save_dedup_supersede_forget_history_on_real_pgvector(store):
    """16a : dédup sémantique, supersede, soft delete, recall courant vs historique."""
    first = await store.save("profil de risque prudent", None)
    assert first.duplicate is False
    dup = await store.save("profil de risque prudent", None)
    assert dup.duplicate is True
    assert dup.id == first.id

    new_id = await store.supersede(first.id, "profil de risque modéré", None)
    assert new_id != first.id

    # recall par défaut : uniquement le courant
    current = await store.recall("profil de risque", k=5)
    assert [r["content"] for r in current] == ["profil de risque modéré"]
    assert current[0]["valid_until"] is None
    assert current[0]["provenance"] == "agent"

    # avec historique : les deux versions, archivées marquées
    full = await store.recall("profil de risque", k=5, include_history=True)
    assert len(full) == 2
    archived = next(r for r in full if r["id"] == first.id)
    assert archived["valid_until"] is not None

    # history : chaîne complète, la plus récente d'abord
    hist = await store.history(new_id)
    assert [h["content"] for h in hist] == [
        "profil de risque modéré",
        "profil de risque prudent",
    ]

    # forget = soft delete, la ligne reste en base
    assert await store.forget(new_id) is True
    assert await store.recall("profil de risque modéré", k=5) == []
    still_there = await store.recall(
        "profil de risque modéré", k=5, include_history=True
    )
    assert len(still_there) == 1
    assert await store.forget(new_id) is False  # déjà archivé

    # supersede sur un id archivé -> ValueError
    with pytest.raises(ValueError):
        await store.supersede(first.id, "autre version", None)


async def test_23e_save_scrub_secret_avant_insert(store):
    """23e : un secret n'atteint jamais la base (ni en clair, ni embeddé)."""
    result = await store.save("ma clé sk-ant-abcdef1234567890xx est ici", None)
    assert result.redacted is True
    recalled = await store.recall("ma clé", k=5, include_history=True)
    row = next(r for r in recalled if r["id"] == result.id)
    assert "sk-ant-" not in row["content"]
    assert REDACTED in row["content"]


async def test_23e_save_zone_intermediaire_supersede_auto(store):
    """23e : cos dans [0.85, 0.97) -> ancien archivé (superseded_by)."""
    v1 = [1.0] + [0.0] * 1535
    v2 = [0.9, math.sqrt(1 - 0.81)] + [0.0] * 1534  # cos(v1, v2) = 0.9
    r1 = await store.save("fait A v1", v1)
    assert r1.superseded is None and r1.duplicate is False
    r2 = await store.save("fait A v2", v2)
    assert r2.duplicate is False
    assert r2.superseded == r1.id
    # l'ancien a valid_until + superseded_by en base
    async with store._session_factory() as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT valid_until IS NOT NULL AS archived, "
                        "superseded_by::text FROM memories WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": r1.id},
                )
            )
            .mappings()
            .one()
        )
    assert row["archived"] is True
    assert row["superseded_by"] == r2.id
    # recall courant : seul le nouveau ; historique : les deux
    current = await store.recall("fait A", k=5)
    assert all(r["id"] != r1.id for r in current)
    full = await store.recall("fait A", k=5, include_history=True)
    assert {r["id"] for r in full} >= {r1.id, r2.id}


async def test_23e_purge_hard_delete_plus_audit_redacted(store):
    """23e : purge = DELETE réel + ligne d'audit avec contenu masqué."""
    r = await store.save("secret sk-ant-abcdef1234567890zz", None)
    assert r.redacted is True
    assert await store.purge(r.id, reason="demande RGPD") is True
    # la ligne est vraiment supprimée
    assert await store.recall("secret", k=5, include_history=True) == []
    assert await store.history(r.id) == []
    # l'audit existe, avec le contenu redacted et la raison
    async with store._session_factory() as session:
        audit = (
            (
                await session.execute(
                    text(
                        "SELECT memory_id::text, content_redacted, reason, purged_at "
                        "FROM memory_purge_audit WHERE memory_id = CAST(:id AS uuid)"
                    ),
                    {"id": r.id},
                )
            )
            .mappings()
            .all()
        )
    assert len(audit) == 1
    assert audit[0]["memory_id"] == r.id
    assert audit[0]["reason"] == "demande RGPD"
    assert "sk-ant-" not in audit[0]["content_redacted"]
    assert REDACTED in audit[0]["content_redacted"]
    assert audit[0]["purged_at"] is not None
    # purge d'un id inconnu -> False, aucun audit
    assert await store.purge("00000000-0000-0000-0000-000000000000", "x") is False
