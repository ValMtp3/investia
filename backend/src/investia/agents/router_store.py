"""Store pgvector des feedbacks du routeur d'agents A2A (étape 18a).

Même pattern que DbRouterFeedback (12h) : SQL raw + pgvector cosinus,
embeddings existants (text-embedding-3-small, 1536 dimensions). Chaque
feedback enregistre la question, la liste des agents délégués (JSON) et le
succès du run ; `neighbors` renvoie les voisins avec leur agent individuel.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.agents.router import K_NEIGHBORS, AgentFeedbackStore, AgentNeighbor
from investia.memory.embeddings import Embeddings


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


class DbAgentFeedback(AgentFeedbackStore):
    """Feedbacks (question, agents, succès) en PostgreSQL, recherchés par k-NN.

    Une ligne = un run multi-agent ; `agents` est un JSON array. `neighbors`
    aplati chaque ligne en un voisin par agent (pour le scoring du routeur).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        embeddings: Embeddings,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings

    async def record(self, question: str, agents: list[str], success: bool) -> None:
        vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO agent_feedback (question, agents, success, embedding) "
                    "VALUES (:q, :a, :s, CAST(:e AS vector))"
                ),
                {
                    "q": question,
                    "a": json.dumps(list(agents), ensure_ascii=False),
                    "s": success,
                    "e": _vector_literal(vector),
                },
            )
            await session.commit()

    async def neighbors(
        self, question: str, k: int = K_NEIGHBORS
    ) -> list[AgentNeighbor]:
        query_vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT agents, success, "
                            "1 - (embedding <=> CAST(:e AS vector)) AS similarity "
                            "FROM agent_feedback "
                            "ORDER BY embedding <=> CAST(:e AS vector) LIMIT :k"
                        ),
                        {"e": _vector_literal(query_vector), "k": k},
                    )
                )
                .mappings()
                .all()
            )
        neighbors: list[AgentNeighbor] = []
        for row in rows:
            similarity = float(row["similarity"])
            success = bool(row["success"])
            try:
                agents = json.loads(str(row["agents"]))
            except (json.JSONDecodeError, TypeError):
                continue
            for agent in agents:
                neighbors.append(
                    AgentNeighbor(
                        similarity=similarity, agent=str(agent), success=success
                    )
                )
        return neighbors


__all__ = ["DbAgentFeedback"]
