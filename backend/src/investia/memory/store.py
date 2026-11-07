"""Stockage de la mémoire longue en PostgreSQL (pgvector, similarité cosinus)."""

from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.memory.embeddings import Embeddings


class MemoryStoreProtocol(Protocol):
    async def save(self, content: str, embedding: list[float] | None) -> str: ...

    async def recall(self, query: str, k: int = 5) -> list[dict[str, Any]]: ...


class DbMemoryStore:
    def __init__(
        self, session_factory: async_sessionmaker, embeddings: Embeddings
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings

    async def save(self, content: str, embedding: list[float] | None = None) -> str:
        vector = embedding or (await self._embeddings.embed([content]))[0]
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "INSERT INTO memories (content, embedding) "
                    "VALUES (:c, CAST(:e AS vector)) RETURNING id::text"
                ),
                {"c": content, "e": "[" + ",".join(str(v) for v in vector) + "]"},
            )
            memory_id = result.scalar_one()
            await session.commit()
            return memory_id

    async def recall(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        query_vector = (await self._embeddings.embed([query]))[0]
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT content, "
                            "1 - (embedding <=> CAST(:e AS vector)) AS score "
                            "FROM memories "
                            "ORDER BY embedding <=> CAST(:e AS vector) LIMIT :k"
                        ),
                        {
                            "e": "[" + ",".join(str(v) for v in query_vector) + "]",
                            "k": k,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [
                {"content": row["content"], "score": float(row["score"])}
                for row in rows
            ]
