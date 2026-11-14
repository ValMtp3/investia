"""Stockage de la mémoire longue en PostgreSQL (pgvector, similarité cosinus).

Schéma temporel (16a) : chaque souvenir a une période de validité
(`valid_from`/`valid_until`), une provenance, un scope, et peut être remplacé
par une version plus récente (`superseded_by`) ou « oublié » (soft delete).
Aucune ligne n'est jamais supprimée : l'historique reste en base.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.memory.embeddings import Embeddings

# Seuil de cosinus au-delà duquel un save est un doublon sémantique (idempotent).
DEDUP_THRESHOLD = 0.97


@dataclass(frozen=True)
class SaveResult:
    id: str
    duplicate: bool


class MemoryStoreProtocol(Protocol):
    async def save(
        self,
        content: str,
        embedding: list[float] | None,
        *,
        provenance: str = "agent",
        scope: str = "global",
        dedup_threshold: float = DEDUP_THRESHOLD,
    ) -> SaveResult: ...

    async def supersede(
        self,
        old_id: str,
        new_content: str,
        embedding: list[float] | None = None,
        *,
        provenance: str = "agent",
        scope: str = "global",
    ) -> str: ...

    async def forget(self, memory_id: str) -> bool: ...

    async def recall(
        self, query: str, k: int = 5, *, include_history: bool = False
    ) -> list[dict[str, Any]]: ...

    async def history(self, memory_id: str) -> list[dict[str, Any]]: ...


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


class DbMemoryStore:
    def __init__(
        self, session_factory: async_sessionmaker, embeddings: Embeddings
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings

    async def save(
        self,
        content: str,
        embedding: list[float] | None = None,
        *,
        provenance: str = "agent",
        scope: str = "global",
        dedup_threshold: float = DEDUP_THRESHOLD,
    ) -> SaveResult:
        vector = embedding or (await self._embeddings.embed([content]))[0]
        async with self._session_factory() as session:
            # Dédup sémantique : un souvenir courant quasi identique existe déjà
            # -> on ne réinsère rien, on rend son id (écriture idempotente).
            existing = await session.execute(
                text(
                    "SELECT id::text FROM memories "
                    "WHERE valid_until IS NULL "
                    "ORDER BY embedding <=> CAST(:e AS vector) LIMIT 1"
                ),
                {"e": _vector_literal(vector)},
            )
            nearest_id = existing.scalar_one_or_none()
            if nearest_id is not None:
                nearest_score = await session.execute(
                    text(
                        "SELECT 1 - (embedding <=> CAST(:e AS vector)) AS score "
                        "FROM memories WHERE id = CAST(:id AS uuid)"
                    ),
                    {"e": _vector_literal(vector), "id": nearest_id},
                )
                if float(nearest_score.scalar_one()) >= dedup_threshold:
                    return SaveResult(id=nearest_id, duplicate=True)
            result = await session.execute(
                text(
                    "INSERT INTO memories (content, embedding, provenance, scope, "
                    "valid_from) VALUES (:c, CAST(:e AS vector), :p, :s, now()) "
                    "RETURNING id::text"
                ),
                {
                    "c": content,
                    "e": _vector_literal(vector),
                    "p": provenance,
                    "s": scope,
                },
            )
            memory_id = result.scalar_one()
            await session.commit()
            return SaveResult(id=memory_id, duplicate=False)

    async def supersede(
        self,
        old_id: str,
        new_content: str,
        embedding: list[float] | None = None,
        *,
        provenance: str = "agent",
        scope: str = "global",
    ) -> str:
        vector = embedding or (await self._embeddings.embed([new_content]))[0]
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "INSERT INTO memories (content, embedding, provenance, scope, "
                        "valid_from) VALUES (:c, CAST(:e AS vector), :p, :s, now()) "
                        "RETURNING id::text"
                    ),
                    {
                        "c": new_content,
                        "e": _vector_literal(vector),
                        "p": provenance,
                        "s": scope,
                    },
                )
                new_id = result.scalar_one()
                archived = await session.execute(
                    text(
                        "UPDATE memories SET valid_until = now(), superseded_by = "
                        "CAST(:new AS uuid) WHERE id = CAST(:old AS uuid) "
                        "AND valid_until IS NULL"
                    ),
                    {"new": new_id, "old": old_id},
                )
                if archived.rowcount != 1:
                    raise ValueError(f"souvenir inconnu ou déjà archivé: {old_id}")
            return new_id

    async def forget(self, memory_id: str) -> bool:
        """Soft delete : valid_until = now(), la ligne reste en base."""
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "UPDATE memories SET valid_until = now() "
                    "WHERE id = CAST(:id AS uuid) AND valid_until IS NULL"
                ),
                {"id": memory_id},
            )
            await session.commit()
            return result.rowcount == 1

    async def recall(
        self, query: str, k: int = 5, *, include_history: bool = False
    ) -> list[dict[str, Any]]:
        query_vector = (await self._embeddings.embed([query]))[0]
        validity_filter = "" if include_history else "WHERE valid_until IS NULL"
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id::text, content, provenance, scope, valid_from, "
                            "valid_until, "
                            "1 - (embedding <=> CAST(:e AS vector)) AS score "
                            f"FROM memories {validity_filter} "
                            "ORDER BY embedding <=> CAST(:e AS vector) LIMIT :k"
                        ),
                        {
                            "e": _vector_literal(query_vector),
                            "k": k,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [_public_row(row) for row in rows]

    async def history(self, memory_id: str) -> list[dict[str, Any]]:
        """Toute la chaîne de versions contenant `memory_id` (via superseded_by),
        la plus récente d'abord. La table memories reste petite (mémoire longue),
        on reconstruit la chaîne en Python plutôt qu'en CTE récursive à deux sens."""
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id::text, content, provenance, scope, valid_from, "
                            "valid_until, superseded_by::text FROM memories"
                        )
                    )
                )
                .mappings()
                .all()
            )
        by_id = {row["id"]: row for row in rows}
        if memory_id not in by_id:
            return []
        # Remonter à l'ancêtre le plus ancien (celui que personne ne remplace).
        current = memory_id
        while any(
            row["superseded_by"] == current for row in rows if row["superseded_by"]
        ):
            current = next(row["id"] for row in rows if row["superseded_by"] == current)
        # Redescendre la chaîne, la plus récente d'abord.
        chain = []
        while current is not None:
            chain.append(_public_row(by_id[current]))
            current = by_id[current]["superseded_by"]
        chain.reverse()
        return chain


def _public_row(row: Any) -> dict[str, Any]:
    valid_from: datetime = row["valid_from"]
    valid_until: datetime | None = row["valid_until"]
    result: dict[str, Any] = {
        "id": row["id"],
        "content": row["content"],
        "provenance": row["provenance"],
        "scope": row["scope"],
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until is not None else None,
    }
    if "score" in row.keys():
        result["score"] = float(row["score"])
    return result
