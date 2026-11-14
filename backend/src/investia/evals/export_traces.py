"""Export read-only des traces en dataset JSONL versionné (spec 14b).

Utilise uniquement list_runs/get_run du store : aucune écriture en base.
Produit `<out>.jsonl` (une ligne JSON par run) + `<out>.jsonl.sha256`.
Sert à la revue humaine des échecs et aux futurs comparatifs A/B en mode live.

CLI : uv run python -m investia.evals.export_traces
       [--out PATH] [--status blocked,max_turns] [--limit 200]
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

EVALS_DIR = Path(__file__).resolve().parents[4] / "evals"
DEFAULT_OUT = EVALS_DIR / "generated" / "traces_dataset.jsonl"


async def export_dataset(
    store: Any,
    out_path: str | Path,
    statuses: tuple[str, ...] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Exporte les runs du store en JSONL + hash. Lecture seule, déterministe."""
    runs = await store.list_runs(limit)
    if statuses:
        wanted = set(statuses)
        runs = [run for run in runs if run.get("status") in wanted]
    runs = sorted(
        runs,
        key=lambda run: (str(run.get("created_at", "")), str(run.get("id", ""))),
        reverse=True,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for run in runs:
        detail = await store.get_run(str(run["id"]))
        steps = detail.get("steps") or []
        entry = {
            "id": str(run["id"]),
            "question": run.get("question"),
            "answer": (detail.get("run") or {}).get("answer"),
            "model": run.get("model"),
            "status": run.get("status"),
            "turns": run.get("turns"),
            "total_cost_cents": run.get("total_cost_cents"),
            "created_at": str(run.get("created_at")),
            "step_kinds": [step.get("kind") for step in steps],
        }
        lines.append(json.dumps(entry, ensure_ascii=False, default=str))
    content = "\n".join(lines) + ("\n" if lines else "")
    out_path.write_text(content, encoding="utf-8")
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    out_path.with_suffix(out_path.suffix + ".sha256").write_text(
        sha256 + "\n", encoding="utf-8"
    )
    return {"path": str(out_path), "count": len(lines), "sha256": sha256}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="investia.evals.export_traces",
        description="Export read-only des traces en dataset JSONL + SHA-256",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="chemin du JSONL")
    parser.add_argument(
        "--status",
        default="",
        help="statuts séparés par des virgules (ex. blocked,max_turns) ; vide = tout",
    )
    parser.add_argument("--limit", type=int, default=200, help="nb max de runs")
    args = parser.parse_args(argv)
    statuses = tuple(s for s in args.status.split(",") if s) or None

    async def _run() -> int:
        # Imports lazy : --help fonctionne sans base de données.
        from investia.db import get_session
        from investia.tracing.store import DbTraceStore

        store = DbTraceStore(get_session())
        info = await export_dataset(
            store, args.out, statuses=statuses, limit=args.limit
        )
        print(
            f"{info['count']} runs exportés dans {info['path']} "
            f"(sha256 {info['sha256'][:12]}…)"
        )
        return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
