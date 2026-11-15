"""TraceStore : enregistre les exécutions (runs) et leurs étapes en PostgreSQL.

Schéma (migration 0002) : `runs` + `run_steps` (payload JSONB tronqué à 4 Ko).
Depuis la spec 13a, toute donnée stockée (question, payload, réponse) passe
par un redactor PII/secrets avant l'INSERT — voir `investia.redaction`.
"""

import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.redaction import Redactor, default_redactor, redact_value

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

    # 23f : journal des événements SSE d'un run (replay Last-Event-ID)
    async def append_event(
        self, run_id: str, seq: int, event: str, payload: dict
    ) -> None: ...

    async def events_after(
        self, run_id: str, last_seq: int
    ) -> list[dict[str, Any]]: ...


def _truncate(payload: dict[str, Any]) -> dict[str, Any]:
    blob = json.dumps(payload, default=str, ensure_ascii=False)
    if len(blob) <= MAX_PAYLOAD_CHARS:
        return payload
    return {"_truncated": True, "_head": blob[:MAX_PAYLOAD_CHARS]}


class DbTraceStore:
    """Store réel en PostgreSQL (async). Redacte PII/secrets avant stockage."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        redactor: Redactor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redactor = redactor if redactor is not None else default_redactor()

    async def start_run(self, question: str) -> str:
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "INSERT INTO runs (question, status) VALUES (:q, 'running') "
                    "RETURNING id::text"
                ),
                {"q": self._redactor.redact(question)},
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
                    "payload": json.dumps(
                        _truncate(redact_value(payload, self._redactor)),
                        ensure_ascii=False,
                    ),
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
                    "a": self._redactor.redact(answer)[:MAX_PAYLOAD_CHARS],
                    "m": model,
                    "t": turns,
                    "c": cost_cents,
                    "s": status,
                },
            )
            await session.commit()

    async def append_event(
        self, run_id: str, seq: int, event: str, payload: dict
    ) -> None:
        """23f : persiste un événement SSE d'un run (idempotent sur (run_id, seq))."""
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO run_events (run_id, seq, event, payload) "
                    "VALUES (CAST(:r AS uuid), :s, :e, CAST(:p AS jsonb)) "
                    "ON CONFLICT (run_id, seq) DO NOTHING"
                ),
                {
                    "r": run_id,
                    "s": seq,
                    "e": event,
                    "p": json.dumps(
                        redact_value(payload, self._redactor), ensure_ascii=False
                    ),
                },
            )
            await session.commit()

    async def events_after(self, run_id: str, last_seq: int) -> list[dict[str, Any]]:
        """23f : événements stockés du run avec seq > last_seq, ordre croissant."""
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT seq, event, payload FROM run_events "
                            "WHERE run_id = CAST(:r AS uuid) AND seq > :s ORDER BY seq"
                        ),
                        {"r": run_id, "s": last_seq},
                    )
                )
                .mappings()
                .all()
            )
        return [
            {
                "seq": int(row["seq"]),
                "event": str(row["event"]),
                "payload": dict(row["payload"]),
            }
            for row in rows
        ]

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Exécutions récentes (sans la réponse, réservée au détail)."""
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id::text AS id, question, status, model, turns, "
                            "total_cost_cents, created_at FROM runs "
                            "ORDER BY created_at DESC, id DESC LIMIT :limit"
                        ),
                        {"limit": limit},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

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
                            "SELECT turn, kind, payload, created_at FROM run_steps "
                            "WHERE run_id = :rid ORDER BY id"
                        ),
                        {"rid": UUID(run_id)},
                    )
                )
                .mappings()
                .all()
            )
            # Spans OTel GenAI du run (étape 9) : table absente avant la migration
            # 0006 → on tolère l'erreur et renvoie une liste vide.
            try:
                spans = (
                    (
                        await session.execute(
                            text(
                                "SELECT name, start_ts, end_ts, attributes, "
                                "status, error "
                                "FROM otel_spans WHERE run_id = :rid "
                                "ORDER BY start_ts"
                            ),
                            {"rid": UUID(run_id)},
                        )
                    )
                    .mappings()
                    .all()
                )
            except Exception:
                spans = []
            return {
                "run": dict(run) if run else None,
                "steps": [dict(s) for s in steps],
                "spans": [dict(s) for s in spans],
            }
