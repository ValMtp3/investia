"""Lance le runner d'evals mock sur le dataset pinné et produit results.json (23h).

Usage :
    uv run python run_benchmark.py                     # dataset par défaut pinné
    uv run python run_benchmark.py --cases PATH        # ex. cases-live pinné
    uv run python run_benchmark.py --sha256 <hex>      # vérifie le pin avant le run
    uv run python run_benchmark.py --out results.json  # chemin de sortie

Le sha256 du dataset est vérifié (sidecar <cases>.sha256 ou --sha256) puis
enregistré dans results.json : deux runs avec le même dataset_sha256 sont
comparables (pattern Harbor / Terminal-Bench 4.1, arXiv 2611.08417).
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from investia.evals.runner import load_cases, run_evals

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = REPO_ROOT / "evals" / "cases.yaml"
DEFAULT_OUT = Path(__file__).resolve().parent / "results.json"
AGENT_NAME = "investia-harness"

# Métriques "gate" : un cas passe si elles valent toutes 1.0 (pass@1 binaire).
GATE_METRICS = (
    "tool_used",
    "numbers_sourced",
    "format_ok",
    "language_ok",
    "disclaimer_ok",
    "plan_suivi",
    "safety_llm_ok",
    "safety_logprobs_ok",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_dataset(cases_path: Path, expected: str | None = None) -> str:
    """Retourne le sha256 réel ; lève SystemExit(1) si le pin ne matche pas."""
    if not cases_path.exists():
        print(f"ERREUR : dataset introuvable : {cases_path}", file=sys.stderr)
        raise SystemExit(1)
    actual = sha256_file(cases_path)
    if expected is None:
        sidecar = Path(str(cases_path) + ".sha256")
        if sidecar.exists():
            expected = sidecar.read_text(encoding="utf-8").strip()
    if expected is not None and actual != expected:
        print(
            f"ECHEC pinning : {cases_path} attendu {expected[:12]}…, "
            f"obtenu {actual[:12]}… (dataset modifié depuis le pin)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return actual


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def build_report(
    summary: dict, dataset_sha256: str, commit: str, duration_ms: float
) -> dict:
    """Agrège le summary du runner mock en rapport type benchmark (pass@1)."""
    results = summary["results"]
    n_cases = len(results)
    metrics_sum: dict[str, float] = {}
    n_pass = 0
    for entry in results:
        metrics = entry["metrics"]
        for name, score in metrics.items():
            metrics_sum[name] = metrics_sum.get(name, 0.0) + float(score)
        if all(metrics.get(g, 0.0) == 1.0 for g in GATE_METRICS):
            n_pass += 1
    metrics_mean = {
        name: round(total / n_cases, 4) for name, total in metrics_sum.items()
    }
    return {
        "agent": AGENT_NAME,
        "commit": commit,
        "dataset_sha256": dataset_sha256,
        "n_cases": n_cases,
        "pass1": round(n_pass / n_cases, 4) if n_cases else 0.0,
        "metrics": metrics_mean,
        "cost_cents_total": 0.0,  # mode mock : aucun appel LLM, coût nul
        "duration_ms": round(duration_ms, 1),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


async def run_benchmark(cases_path: Path) -> dict:
    cases = load_cases(cases_path)
    t0 = time.perf_counter()
    summary = await run_evals(cases, mode="mock")
    duration_ms = (time.perf_counter() - t0) * 1000.0
    dataset_sha256 = verify_dataset(cases_path)
    return build_report(summary, dataset_sha256, git_commit(), duration_ms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark mock pinné du harness Investia -> results.json (23h)"
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
        help="fichier de cas YAML (défaut : evals/cases.yaml pinné)",
    )
    parser.add_argument(
        "--sha256",
        default=None,
        help="sha256 attendu du dataset (sinon lu dans <cases>.sha256)",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="results.json de sortie"
    )
    args = parser.parse_args(argv)
    if args.sha256 is not None:
        verify_dataset(args.cases, args.sha256)
    report = asyncio.run(run_benchmark(args.cases))
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"OK : {args.out} — pass@1={report['pass1']} sur {report['n_cases']} cas "
        f"(dataset {report['dataset_sha256'][:12]}…, commit {report['commit'][:8]})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
