"""Tests TDD de la brique 12e : cache sémantique (DbSemanticCache + boucle + evals)."""

import math
from typing import Any

import pytest

from investia.agent.semantic_cache import CACHE_THRESHOLD, DbSemanticCache


class FakeEmbeddings:
    """Embeddings déterministes : hash du texte, vecteur normalisé."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [b / 255.0 for b in digest[:8]]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec] + [0.0] * 1528)
        return vectors


class FakeSemanticCache:
    """Cache en mémoire avec vraie similarité cosinus (pour tester la boucle)."""

    def __init__(self, threshold: float = CACHE_THRESHOLD):
        self.threshold = threshold
        self.entries: list[tuple[str, str, list[float]]] = []
        self.stored: list[tuple[str, str]] = []

    @staticmethod
    def _cos(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)

    async def lookup(self, question: str) -> str | None:
        qv = (await FakeEmbeddings().embed([question]))[0]
        best, best_score = None, -1.0
        for q, answer, vec in self.entries:
            score = self._cos(qv, vec)
            if score > best_score:
                best, best_score = answer, score
        if best is not None and best_score >= self.threshold:
            return best
        return None

    async def store(self, question: str, answer: str) -> None:
        vec = (await FakeEmbeddings().embed([question]))[0]
        self.entries.append((question, answer, vec))
        self.stored.append((question, answer))


def test_seuil_par_defaut_092():
    assert CACHE_THRESHOLD == 0.92


@pytest.mark.integration
async def test_integration_lookup_store_roundtrip():
    """Roundtrip réel sur pgvector : store puis lookup (identique -> hit, loin -> miss)."""
    from investia.db import get_session
    from investia.memory.embeddings import FakeEmbeddingsForTests

    cache = DbSemanticCache(get_session(), FakeEmbeddingsForTests())
    await cache.store("prix de AAPL ?", "AAPL vaut 344.63 $")
    hit = await cache.lookup("prix de AAPL ?")
    assert hit == "AAPL vaut 344.63 $"
    miss = await cache.lookup("quelle météo à Paris demain ?")
    assert miss is None
