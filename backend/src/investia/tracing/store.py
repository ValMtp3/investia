"""TraceStore : enregistre les exécutions (runs) et leurs étapes en PostgreSQL.

Schéma (migration 0002) : `runs` + `run_steps` (payload JSONB tronqué à 4 Ko).
Aucun secret n'est jamais loggué (les clés API ne passent pas par ici).
"""

import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

MAX_PAYLOAD_CHARS = 4096


class TraceStoreProtocol(Protocol):
    async def start_run(self, question: str) -> str: ...

    async def log_step(
        self, run_id: str, turn: int, kind: str, payload: dict
    ) -> None: ...

    async def finish_run(
        self,
        run_id: str,
        *,
        answer: str,
        model: str,
        turns: int,
        cost_cents: float,
        status: str,
    ) -> None: ...


def _truncate(payload: dict[str, Any]) -> dict[str, Any]:
    blob = json.dumps(payload, default=str, ensure_ascii=False)
    if len(blob) <= MAX_PAYLOAD_CHARS:
        return payload
    return {"_truncated": True, "_head": blob[:MAX_PAYLOAD_CHARS]}


class DbTraceStore:
    """Store réel en PostgreSQL (async)."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def start_run(self, question: str) -> str:
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "INSERT INTO runs (question, status) VALUES (:q, 'running') "
                    "RETURNING id::text"
                ),
                {"q": question},
            )
            run_id = result.scalar_one()
            await session.commit()
            return run_id

    async def log_step(self, run_id: str, turn: int, kind: str, payload: dict) -> None:
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO run_steps (run_id, turn, kind, payload) "
                    "VALUES (:rid, :turn, :kind, CAST(:payload AS jsonb))"
                ),
                {
                    "rid": UUID(run_id),
                    "turn": turn,
                    "kind": kind,
                    "payload": json.dumps(_truncate(payload), ensure_ascii=False),
                },
            )
            await session.commit()

    async def finish_run(
        self,
        run_id: str,
        *,
        answer: str,
        model: str,
        turns: int,
        cost_cents: float,
        status: str,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "UPDATE runs SET answer=:a, model=:m, turns=:t, "
                    "total_cost_cents=:c, status=:s WHERE id=:rid"
                ),
                {
                    "rid": UUID(run_id),
                    "a": answer[:MAX_PAYLOAD_CHARS],
                    "m": model,
                    "t": turns,
                    "c": cost_cents,
                    "s": status,
                },
            )
            await session.commit()

    async def get_run(self, run_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            run = (
                (
                    await session.execute(
                        text("SELECT * FROM runs WHERE id = :rid"),
                        {"rid": UUID(run_id)},
                    )
                )
                .mappings()
                .first()
            )
            steps = (
                (
                    await session.execute(
                        text(
                            "SELECT turn, kind, payload FROM run_steps "
                            "WHERE run_id = :rid ORDER BY id"
                        ),
                        {"rid": UUID(run_id)},
                    )
                )
                .mappings()
                .all()
            )
            return {
                "run": dict(run) if run else None,
                "steps": [dict(s) for s in steps],
            }
