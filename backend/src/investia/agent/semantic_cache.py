"""Cache sémantique des réponses de l'agent (étape 12e).

Une question très proche d'une question déjà répondue (similarité cosinus
>= CACHE_THRESHOLD) est servie sans appel LLM. On ne stocke que des réponses
qui ont passé les garde-fous (status ok) — la responsabilité du store est à
l'appelant (la boucle).
"""

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.memory.embeddings import Embeddings

# Seuil haut : en finance, deux questions proches ne sont pas identiques.
CACHE_THRESHOLD = 0.92


class SemanticCacheProtocol(Protocol):
    async def lookup(self, question: str) -> str | None: ...

    async def store(self, question: str, answer: str) -> None: ...


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


class DbSemanticCache:
    """Cache sémantique en PostgreSQL (pgvector), même pattern que DbMemoryStore."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        embeddings: Embeddings,
        threshold: float = CACHE_THRESHOLD,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._threshold = threshold

    async def lookup(self, question: str) -> str | None:
        query_vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT answer, "
                            "1 - (embedding <=> CAST(:e AS vector)) AS score "
                            "FROM semantic_cache "
                            "ORDER BY embedding <=> CAST(:e AS vector) LIMIT 1"
                        ),
                        {"e": _vector_literal(query_vector)},
                    )
                )
                .mappings()
                .first()
            )
        if row is None or float(row["score"]) < self._threshold:
            return None
        return str(row["answer"])

    async def store(self, question: str, answer: str) -> None:
        vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO semantic_cache (question, answer, embedding) "
                    "VALUES (:q, :a, CAST(:e AS vector))"
                ),
                {"q": question, "a": answer, "e": _vector_literal(vector)},
            )
            await session.commit()


__all__ = ["CACHE_THRESHOLD", "DbSemanticCache", "SemanticCacheProtocol"]
