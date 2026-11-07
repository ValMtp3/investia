"""Lance les 4 approches (maison + LangGraph + Pydantic AI + OpenAI Agents SDK)
sur les cas mock de evals/cases.yaml et produit results.json (étape 6.2/6.3).

Usage :
    uv run python run_evals.py            # mode mock (déterministe, gratuit)
    uv run python run_evals.py --live     # runs réels LLM (budget par défaut 2 €)
"""

import argparse
import json
import time
from pathlib import Path

from investia.agent.loop import AgentResult, ToolCallLog
from investia.evals.metrics import compute_metrics
from investia.evals.runner import MockMarket, load_cases
from investia.tools import build_tools

from impl import langgraph_impl, maison, openai_agents_impl, pydantic_ai_impl

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = REPO_ROOT / "evals" / "cases.yaml"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"

APPROACHES = [
    ("maison", maison.run_case),
    ("langgraph", langgraph_impl.run_case),
    ("pydantic-ai", pydantic_ai_impl.run_case),
    ("openai-agents", openai_agents_impl.run_case),
]


async def run_all(cases, tools) -> dict:
    """Lance chaque approche sur chaque cas, agrège les métriques."""
    per_approach: dict[str, list[dict]] = {}
    for approach, run_case in APPROACHES:
        entries = []
        for case in cases:
            t0 = time.perf_counter()
            outcome = await run_case(
                approach,
                case.id,
                case.question,
                case.expected_tool,
                case.mock_tool_call,
                case.mock_final,
                tools,
            )
            wall_ms = (time.perf_counter() - t0) * 1000
            agent_result = AgentResult(
                answer=outcome.answer,
                turns=1,
                tool_calls=[
                    ToolCallLog(
                        tool=outcome.tool_called or "", arguments={}, ok=outcome.tool_ok
                    )
                ]
                if outcome.tool_called
                else [],
                total_cost_cents=outcome.cost_cents,
                model=approach,
            )
            metrics = compute_metrics(agent_result, case.expected_tool)
            entries.append(
                {
                    "case_id": case.id,
                    "tool_called": outcome.tool_called,
                    "tool_ok": outcome.tool_ok,
                    "duration_ms": round(wall_ms, 1),
                    "cost_cents": outcome.cost_cents,
                    "error": outcome.error,
                    "metrics": metrics,
                }
            )
        per_approach[approach] = entries
    # agrégats par approche
    summary = {}
    for approach, entries in per_approach.items():
        n = len(entries)
        summary[approach] = {
            "cases": n,
            "tool_ok_rate": round(sum(1 for e in entries if e["tool_ok"]) / n, 3),
            "avg_duration_ms": round(sum(e["duration_ms"] for e in entries) / n, 1),
            "total_cost_cents": round(sum(e["cost_cents"] for e in entries), 3),
            "errors": sum(1 for e in entries if e["error"]),
            "metrics_avg": {
                m: round(sum(e["metrics"].get(m, 0.0) for e in entries) / n, 3)
                for m in (
                    "tool_used",
                    "numbers_sourced",
                    "format",
                    "langage",
                    "disclaimer",
                )
            },
        }
    return {
        "mode": "mock",
        "cases": [c.id for c in cases],
        "per_approach": per_approach,
        "summary": summary,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="runs LLM réels (non implémenté ici : mock uniquement)",
    )
    args = parser.parse_args()
    if args.live:
        raise SystemExit(
            "mode --live : à faire en 6.3 avec budget 2 € (D62), pas en mock"
        )
    cases = load_cases(CASES_PATH)
    tools = build_tools(MockMarket())
    results = await run_all(cases, tools)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(results["summary"], indent=2, ensure_ascii=False))
    print(f"\n→ {RESULTS_PATH}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
