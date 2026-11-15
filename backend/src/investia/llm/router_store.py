"""Store pgvector des feedbacks du routeur appris (étape 12h) + état LinUCB (23d).

Même pattern que DbSemanticCache (12e) : SQL raw + pgvector cosinus,
embeddings existants (text-embedding-3-small, 1536 dimensions).

23d : `router_feedback` gagne `cost_cents` (migration 0012) et une nouvelle
table `router_linucb` persiste l'état LinUCB par bras (A aplati en
double precision[], b, n) — des tableaux simples, pas besoin de pgvector ici.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.llm.router import K_NEIGHBORS, Neighbor, RouterFeedbackStore
from investia.memory.embeddings import Embeddings


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


def _array_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def _flatten(matrix: list[list[float]]) -> list[float]:
    return [v for row in matrix for v in row]


def _unflatten(flat: list[float], d: int) -> list[list[float]]:
    return [list(flat[i * d : (i + 1) * d]) for i in range(d)]


class DbRouterFeedback(RouterFeedbackStore):
    """Feedbacks (question, modèle, succès) en PostgreSQL, recherchés par k-NN."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        embeddings: Embeddings,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings

    async def record(
        self, question: str, model: str, success: bool, cost_cents: float = 0.0
    ) -> None:
        vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO router_feedback "
                    "(question, model, success, cost_cents, embedding) "
                    "VALUES (:q, :m, :s, :c, CAST(:e AS vector))"
                ),
                {
                    "q": question,
                    "m": model,
                    "s": success,
                    "c": cost_cents,
                    "e": _vector_literal(vector),
                },
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


class DbLinUCBStore:
    """23d : persistance de l'état LinUCB par bras (table router_linucb, 0012).

    A est stocké aplati (d×d → d² floats) ; à la lecture on le remet en matrice.
    """

    def __init__(self, session_factory: async_sessionmaker, d: int = 7) -> None:
        self._session_factory = session_factory
        self._d = d

    async def load_all(self) -> dict[str, dict[str, Any]]:
        async with self._session_factory() as session:
            rows = (
                (await session.execute(text("SELECT arm, a, b, n FROM router_linucb")))
                .mappings()
                .all()
            )
        return {
            str(row["arm"]): {
                "A": _unflatten([float(v) for v in row["a"]], self._d),
                "b": [float(v) for v in row["b"]],
                "n": int(row["n"]),
            }
            for row in rows
        }

    async def save(self, arm: str, state: dict[str, Any]) -> None:
        flat_a = _flatten(state["A"])
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO router_linucb (arm, a, b, n, updated_at) "
                    "VALUES (:arm, CAST(:a AS double precision[]), "
                    "CAST(:b AS double precision[]), :n, now()) "
                    "ON CONFLICT (arm) DO UPDATE SET "
                    "a = EXCLUDED.a, b = EXCLUDED.b, n = EXCLUDED.n, "
                    "updated_at = now()"
                ),
                {
                    "arm": arm,
                    "a": _array_literal(flat_a),
                    "b": _array_literal(list(state["b"])),
                    "n": int(state["n"]),
                },
            )
            await session.commit()

    async def all_feedbacks(self) -> list[dict[str, Any]]:
        """23d : tous les feedbacks (pour la calibration offline), ordre chrono."""
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT question, model, success, cost_cents "
                            "FROM router_feedback ORDER BY created_at"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [
            {
                "question": str(row["question"]),
                "model": str(row["model"]),
                "success": bool(row["success"]),
                "cost_cents": (
                    float(row["cost_cents"]) if row["cost_cents"] is not None else 0.0
                ),
            }
            for row in rows
        ]


__all__ = ["DbLinUCBStore", "DbRouterFeedback"]
