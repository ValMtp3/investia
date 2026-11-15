"""Commande unique : uv run python -m investia.evals [--mock] [--live] [--cases PATH].

Mode mock (défaut) : déterministe, zéro réseau, tous les cas.
Mode --live (22a) : vrais LLM/market via build_llm_client/build_market_service,
--limit cas (défaut 20, max 100) — à lancer sur le VPS (clés réelles), jamais en CI.
"""

import argparse
import asyncio
import sys

from investia.db import get_session
from investia.evals import EvalStore, load_cases, run_evals
from investia.evals.runner import (
    FakePdfReader,
    FakePythonSandbox,
    FakeWebSearcher,
    MockMarket,
)
from investia.portfolio.service import PortfolioService

MAX_LIVE_LIMIT = 100  # garde-fou batch live (spec 22a)


def _limit_arg(value: str) -> int:
    n = int(value)
    if n < 1 or n > MAX_LIVE_LIMIT:
        raise argparse.ArgumentTypeError(
            f"--limit doit être entre 1 et {MAX_LIVE_LIMIT} (garde-fou batch live 22a)"
        )
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="investia.evals", description="Lancer les evals de l'agent"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=True,
        help="mode mock (défaut, déterministe)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="mode live : vrais LLM/market (VPS uniquement, clés réelles)",
    )
    parser.add_argument("--cases", default=None, help="chemin du fichier de cas YAML")
    parser.add_argument(
        "--limit",
        type=_limit_arg,
        default=20,
        help=f"nb max de cas en mode --live (défaut 20, max {MAX_LIVE_LIMIT})",
    )
    return parser


def _verify_main(argv: list[str]) -> int:
    """23h : `verify --cases PATH [--sha256 H]` — vérifie le dataset pinné."""
    import hashlib
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="investia.evals verify",
        description="Vérifie le sha256 d'un fichier de cas (dataset pinning, 23h)",
    )
    parser.add_argument("--cases", required=True, help="chemin du fichier de cas YAML")
    parser.add_argument(
        "--sha256",
        default=None,
        help="hash attendu ; sinon lu dans <cases>.sha256 à côté du fichier",
    )
    args = parser.parse_args(argv)
    path = Path(args.cases)
    if not path.exists():
        print(f"ERREUR : {path} introuvable")
        return 1
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = args.sha256
    if expected is None:
        sidecar = Path(str(path) + ".sha256")
        if not sidecar.exists():
            print(f"ERREUR : ni --sha256 ni {sidecar}")
            return 1
        expected = sidecar.read_text(encoding="utf-8").strip()
    if actual == expected:
        print(f"OK : {path} (sha256 {actual[:12]}…)")
        return 0
    print(f"ECHEC : {path} — attendu {expected[:12]}…, obtenu {actual[:12]}…")
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "verify":
        return _verify_main(argv[1:])
    args = build_parser().parse_args(argv)
    cases = load_cases(args.cases)
    store = EvalStore(get_session())

    if args.live:
        # 22a : batch live — vrais services, zéro fake. Le plafond budget par
        # appel (17f) reste actif ; ne se lance que là où les clés sont présentes.
        from investia.config import get_settings
        from investia.llm import build_llm_client
        from investia.market import build_market_service

        settings = get_settings()
        llm = build_llm_client(settings)
        market = build_market_service(settings)
        portfolio_service = PortfolioService(get_session(), market)
        cases = cases[: args.limit]
        print(f"batch live : {len(cases)} cas, plafond budget actif (17f)")
        summary = asyncio.run(
            run_evals(
                cases,
                eval_store=store,
                mode="live",
                llm=llm,
                market=market,
                portfolio_service=portfolio_service,
                cases_path=args.cases,  # 23h : dataset pinning
            )
        )
    else:
        # mock (défaut, zéro régression) : tous les cas, fakes déterministes.
        portfolio_service = PortfolioService(get_session(), MockMarket())
        summary = asyncio.run(
            run_evals(
                cases,
                eval_store=store,
                mode="mock",
                portfolio_service=portfolio_service,
                web_searcher=FakeWebSearcher(),
                pdf_reader=FakePdfReader(),
                python_sandbox=FakePythonSandbox(),
                cases_path=args.cases,  # 23h : dataset pinning
            )
        )

    n_cases = len(summary["results"])
    print(f"eval run {summary['run_id']} ({summary['mode']}) — {n_cases} cas")
    for entry in summary["results"]:
        scores = ", ".join(f"{k}={v:g}" for k, v in entry["metrics"].items())
        print(f"  {entry['case_id']}: {scores}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
