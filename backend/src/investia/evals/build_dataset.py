"""Construit un jeu de cas d'evals depuis les traces exportées (spec 22a).

JSONL (export 14b, champ tools_used ajouté en 22a) -> cases-live.yaml
compatible `load_cases` : filtre status + question/answer non vides,
dédup par question normalisée (garde la plus récente), échantillonnage
déterministe (seed), tronqué à --limit. Le YAML généré est relisable tel
quel par `python -m investia.evals --live --cases …`.

CLI : uv run python -m investia.evals.build_dataset
       [--in PATH] [--out PATH] [--limit 50] [--seed 42] [--status ok]
"""

import argparse
import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

EVALS_DIR = Path(__file__).resolve().parents[4] / "evals"
DEFAULT_IN = EVALS_DIR / "generated" / "traces_dataset.jsonl"
DEFAULT_OUT = EVALS_DIR / "generated" / "cases-live.yaml"


def normalize_question(question: str) -> str:
    """Minuscules + espaces collapsés : deux formulations proches = même cas."""
    return " ".join(question.lower().split())


def _trace_to_case(trace: dict[str, Any]) -> dict[str, Any]:
    case: dict[str, Any] = {
        "id": f"trace-{str(trace['id'])[:8]}",
        "question": str(trace["question"]),
        # réponse de référence (lue en mock, comparée en live) — jamais rejouée
        "mock_final": str(trace["answer"]),
    }
    tools_used = trace.get("tools_used") or []
    if tools_used:
        case["expected_tool"] = str(tools_used[0])
    return case


def build_dataset(
    src_path: str | Path,
    out_path: str | Path,
    limit: int = 50,
    seed: int = 42,
    status: str = "ok",
) -> dict[str, Any]:
    """Lit le JSONL de traces, filtre/déduplique, échantillonne, écrit le YAML.

    Déterministe : même entrée + même seed -> YAML byte-identique.
    Lecture seule sur la source ; le fichier de sortie est gitignoré
    (`evals/generated/`).
    """
    src_path = Path(src_path)
    out_path = Path(out_path)
    kept: dict[str, dict[str, Any]] = {}
    for line in src_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        trace = json.loads(line)
        if str(trace.get("status", "")) != status:
            continue
        question = str(trace.get("question") or "").strip()
        answer = str(trace.get("answer") or "").strip()
        if not question or not answer:
            continue
        trace["question"] = question
        trace["answer"] = answer
        # dédup : garde la trace la plus récente par question normalisée
        key = normalize_question(question)
        current = kept.get(key)
        if current is None or str(trace.get("created_at", "")) > str(
            current.get("created_at", "")
        ):
            kept[key] = trace
    traces = sorted(
        kept.values(),
        key=lambda t: (str(t.get("created_at", "")), str(t.get("id", ""))),
        reverse=True,
    )
    rng = random.Random(seed)
    picked = rng.sample(traces, min(limit, len(traces))) if traces else []
    cases = [_trace_to_case(t) for t in picked]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump({"cases": cases}, allow_unicode=True, sort_keys=False)
    out_path.write_text(content, encoding="utf-8")
    # 23h : dataset pinning — sha256 à côté du YAML + changelog (pattern Harbor/TB)
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    Path(str(out_path) + ".sha256").write_text(sha256 + "\n", encoding="utf-8")
    src_sha = hashlib.sha256(src_path.read_bytes()).hexdigest()
    changelog = out_path.parent / "DATASET_CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text(
            "# Changelog des datasets de cas (23h)\n\n"
            "| date UTC | sha256 YAML | nb cas | sha256 source JSONL | limit |\n"
            "|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with changelog.open("a", encoding="utf-8") as handle:
        handle.write(
            f"| {datetime.now(UTC).isoformat(timespec='seconds')} | {sha256} "
            f"| {len(cases)} | {src_sha} | {limit} |\n"
        )
    return {
        "path": str(out_path),
        "count": len(cases),
        "total_ok": len(traces),
        "sha256": sha256,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="investia.evals.build_dataset",
        description="JSONL de traces -> cases-live.yaml (filtré, dédupliqué)",
    )
    parser.add_argument(
        "--in",
        dest="src",
        default=str(DEFAULT_IN),
        help="JSONL d'entrée (export_traces)",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="YAML de sortie")
    parser.add_argument("--limit", type=int, default=50, help="nb max de cas gardés")
    parser.add_argument("--seed", type=int, default=42, help="graine d'échantillonnage")
    parser.add_argument(
        "--status", default="ok", help="statut de run retenu (défaut : ok)"
    )
    args = parser.parse_args(argv)
    info = build_dataset(
        args.src, args.out, limit=args.limit, seed=args.seed, status=args.status
    )
    print(
        f"{info['count']} cas écrits dans {info['path']} "
        f"(sur {info['total_ok']} runs {args.status} dédupliqués)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
