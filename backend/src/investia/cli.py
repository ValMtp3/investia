"""CLI Investia : `uv run python -m investia.cli "question"`."""

import argparse
import asyncio
import sys

from investia.agent import run_agent
from investia.config import get_settings
from investia.db import get_session
from investia.llm import build_llm_client
from investia.llm.errors import LlmError
from investia.market import build_market_service
from investia.market.base import MarketDataError
from investia.memory import build_memory
from investia.tools import build_tools
from investia.tracing import DbTraceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="investia",
        description="Agent IA — simulation, pas un conseil en investissement.",
    )
    parser.add_argument("question", help="question à poser à l'agent")
    parser.add_argument(
        "--max-turns", type=int, default=8, help="tours max de la boucle"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    market = build_market_service(settings)
    memory_store, embeddings = (None, None)
    if settings.openrouter_api_key is not None:
        memory_store, embeddings = build_memory(settings)
    tools = build_tools(market, memory_store=memory_store, embeddings=embeddings)
    llm = build_llm_client(settings)
    try:
        result = asyncio.run(
            run_agent(
                args.question,
                llm,
                tools,
                max_turns=args.max_turns,
                trace_store=DbTraceStore(get_session()),
            )
        )
    except (LlmError, MarketDataError) as error:
        print(f"erreur: {error}", file=sys.stderr)
        return 1
    print(result.answer)
    calls = ", ".join(f"{c.tool}{c.arguments}" for c in result.tool_calls) or "aucun"
    cost = f"{result.total_cost_cents:.3f}c"
    print(f"\n[tours={result.turns} modèle={result.model} outils={calls} coût={cost}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
