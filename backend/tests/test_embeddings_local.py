"""Tests 16b — embeddings locaux (LocalEmbeddings) + choix du backend dans build_memory.

Aucun réseau : un faux module `sentence_transformers` est injecté dans sys.modules.
"""

import math
import sys
import types

import pytest

from investia.memory.embeddings import (
    EMBEDDING_DIM,
    EmbeddingsError,
    LocalEmbeddings,
    pad_to_dim,
)


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# --- pad_to_dim ---------------------------------------------------------------


def test_pad_to_dim_pads_with_zeros_and_preserves_cosine():
    a = [0.6, 0.8]  # norme 1
    b = [1.0, 0.0]
    before = _cos(a, b)
    pa, pb = pad_to_dim(a, EMBEDDING_DIM), pad_to_dim(b, EMBEDDING_DIM)
    assert len(pa) == EMBEDDING_DIM == len(pb)
    assert pa[:2] == a and pa[2:] == [0.0] * (EMBEDDING_DIM - 2)
    assert _cos(pa, pb) == pytest.approx(
        before
    )  # le padding à zéros est exact en cosinus


def test_pad_to_dim_truncates_if_longer():
    v = [0.1] * (EMBEDDING_DIM + 10)
    assert pad_to_dim(v, EMBEDDING_DIM) == [0.1] * EMBEDDING_DIM


def test_pad_to_dim_keeps_short_vector_unchanged_when_already_dim():
    v = [0.5] * EMBEDDING_DIM
    assert pad_to_dim(v, EMBEDDING_DIM) == v


# --- LocalEmbeddings avec faux sentence_transformers --------------------------


class _FakeSentenceTransformer:
    """Encode déterministe : vecteur = hash du texte, normalisé, dim 8."""

    def __init__(self, model_name, device="cpu"):
        self.model_name = model_name
        self.device = device
        self.calls = 0

    def encode(self, texts, normalize_embeddings=True):
        import hashlib

        import numpy as np

        self.calls += 1
        assert normalize_embeddings is True
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [b / 255.0 for b in digest[:8]]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return np.array(out)


@pytest.fixture
def fake_sentence_transformers(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return module


async def test_local_embeddings_returns_normalized_padded_vectors(
    fake_sentence_transformers,
):
    emb = LocalEmbeddings(model_name="fake-model")
    assert emb._model.model_name == "fake-model"
    vectors = await emb.embed(["bonjour", "au revoir"])
    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIM for v in vectors)
    norm = math.sqrt(sum(v * v for v in vectors[0]))
    assert norm == pytest.approx(
        1.0, abs=1e-6
    )  # normalisé (les zéros ne changent pas la norme)
    assert emb._model.calls == 1  # un seul appel au modèle pour tout le batch


async def test_local_embeddings_without_sentence_transformers_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(EmbeddingsError, match="sentence-transformers"):
        LocalEmbeddings(model_name="fake-model")


# --- build_memory : choix du backend ------------------------------------------


def _settings(monkeypatch, backend, model="fake-model"):
    from investia.config import Settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@127.0.0.1:5432/x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://x")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "x")
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("EMBEDDINGS_BACKEND", backend)
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", model)
    import investia.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    return Settings()


def test_build_memory_openrouter_backend_unchanged(monkeypatch):
    from investia.memory import build_memory
    from investia.memory.embeddings import OpenRouterEmbeddings

    settings = _settings(monkeypatch, "openrouter")
    store, embeddings = build_memory(settings)
    assert isinstance(embeddings, OpenRouterEmbeddings)


def test_build_memory_local_backend_uses_local_embeddings(
    monkeypatch, fake_sentence_transformers
):
    from investia.memory import build_memory

    settings = _settings(monkeypatch, "local")
    store, embeddings = build_memory(settings)
    assert isinstance(embeddings, LocalEmbeddings)
    assert embeddings._model.model_name == "fake-model"


def test_build_memory_local_falls_back_to_openrouter_if_unavailable(
    monkeypatch, caplog
):
    from investia.memory import build_memory
    from investia.memory.embeddings import OpenRouterEmbeddings

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    settings = _settings(monkeypatch, "local")
    with caplog.at_level("WARNING"):
        store, embeddings = build_memory(settings)
        assert isinstance(embeddings, OpenRouterEmbeddings)  # fallback, pas de crash
        assert any("fallback" in r.getMessage().lower() for r in caplog.records)


def test_local_embedding_model_name_is_validated(monkeypatch):
    from investia.config import Settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@127.0.0.1:5432/x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://x")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "x")
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "modele; rm -rf /")
    with pytest.raises(ValueError):
        Settings()
