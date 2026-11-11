"""Commande unique : uv run python -m investia.evals [--mock] [--cases PATH]."""

import argparse
import asyncio
import sys

from investia.db import get_session
from investia.evals import EvalStore, load_cases, run_evals
from investia.evals.runner import FakePdfReader, FakeWebSearcher, MockMarket
from investia.portfolio.service import PortfolioService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="investia.evals", description="Lancer les evals de l'agent"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=True,
        help="mode mock (défaut, déterministe)",
    )
    parser.add_argument("--cases", default=None, help="chemin du fichier de cas YAML")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    store = EvalStore(get_session())
    # Portefeuille câblé aussi dans les evals (spec 4.6), valorisé via le marché mock.
    portfolio_service = PortfolioService(get_session(), MockMarket())
    summary = asyncio.run(
        run_evals(
            cases,
            eval_store=store,
            mode="mock",
            portfolio_service=portfolio_service,
            web_searcher=FakeWebSearcher(),
            pdf_reader=FakePdfReader(),
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
