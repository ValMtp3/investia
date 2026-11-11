"""Store pgvector des feedbacks du routeur appris (étape 12h).

Même pattern que DbSemanticCache (12e) : SQL raw + pgvector cosinus,
embeddings existants (text-embedding-3-small, 1536 dimensions).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.llm.router import K_NEIGHBORS, Neighbor, RouterFeedbackStore
from investia.memory.embeddings import Embeddings


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


class DbRouterFeedback(RouterFeedbackStore):
    """Feedbacks (question, modèle, succès) en PostgreSQL, recherchés par k-NN."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        embeddings: Embeddings,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings

    async def record(self, question: str, model: str, success: bool) -> None:
        vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO router_feedback (question, model, success, embedding) "
                    "VALUES (:q, :m, :s, CAST(:e AS vector))"
                ),
                {"q": question, "m": model, "s": success, "e": _vector_literal(vector)},
            )
            await session.commit()

    async def neighbors(self, question: str, k: int = K_NEIGHBORS) -> list[Neighbor]:
        query_vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT model, success, "
                            "1 - (embedding <=> CAST(:e AS vector)) AS similarity "
                            "FROM router_feedback "
                            "ORDER BY embedding <=> CAST(:e AS vector) LIMIT :k"
                        ),
                        {"e": _vector_literal(query_vector), "k": k},
                    )
                )
                .mappings()
                .all()
            )
        return [
            Neighbor(
                similarity=float(row["similarity"]),
                model=str(row["model"]),
                success=bool(row["success"]),
            )
            for row in rows
        ]


__all__ = ["DbRouterFeedback"]
