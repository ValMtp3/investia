"""Tests d'intégration mémoire : vraie table pgvector (conteneur Docker, port 5432)."""

import os
import subprocess
from pathlib import Path

import pytest

from investia.db import get_session
from investia.memory.embeddings import FakeEmbeddingsForTests
from investia.memory.store import DbMemoryStore

pytestmark = pytest.mark.integration

TEST_PG_URL = os.environ.get(
    "TEST_PGVECTOR_URL",
    "postgresql+asyncpg://investia:localtest123@127.0.0.1:5432/investia_test",
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
