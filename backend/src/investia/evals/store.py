"""Stockage des scores d'eval en base (eval_runs / eval_results)."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


class EvalStore:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def start_eval_run(self, model: str, mode: str) -> str:
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "INSERT INTO eval_runs (model, mode) "
                    "VALUES (:m, :mo) RETURNING id::text"
                ),
                {"m": model, "mo": mode},
            )
            run_id = result.scalar_one()
            await session.commit()
            return run_id

    async def log_result(
        self, run_id: str, case_id: str, metric: str, score: float
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO eval_results (run_id, case_id, metric, score, detail) "
                    "VALUES (:rid, :cid, :metric, :score, CAST(:detail AS jsonb))"
                ),
                {
                    "rid": UUID(run_id),
                    "cid": case_id,
                    "metric": metric,
                    "score": score,
                    "detail": json.dumps({}),
                },
            )
            await session.commit()

    async def list_eval_runs(self) -> dict[str, Any]:
        """Runs d'evals (plus récents d'abord) avec leurs résultats."""
        async with self._session_factory() as session:
            runs = (
                (
                    await session.execute(
                        text(
                            "SELECT id::text AS id, started_at, model, commit, mode "
                            "FROM eval_runs ORDER BY started_at DESC, id DESC"
                        )
                    )
                )
                .mappings()
                .all()
            )
            results = (
                (
                    await session.execute(
                        text(
                            "SELECT run_id::text AS run_id, case_id, metric, score "
                            "FROM eval_results ORDER BY id"
                        )
                    )
                )
                .mappings()
                .all()
            )
        by_run: dict[str, list[dict[str, Any]]] = {}
        for row in results:
            result = {
                "case_id": row["case_id"],
                "metric": row["metric"],
                "score": row["score"],
            }
            by_run.setdefault(row["run_id"], []).append(result)
        return {
            "runs": [
                {**dict(run), "results": by_run.get(run["id"], [])} for run in runs
            ]
        }

    async def latest_scores(self) -> dict[str, Any]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT r.case_id, r.metric, r.score, e.started_at "
                            "FROM eval_results r JOIN eval_runs e ON e.id = r.run_id "
                            "ORDER BY e.started_at DESC, r.id DESC"
                        )
                    )
                )
                .mappings()
                .all()
            )
            return {"rows": [dict(row) for row in rows]}
