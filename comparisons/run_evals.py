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

from investia.agent.loop import AgentResult, GuardrailDecision, ToolCallLog
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


async def run_all(
    cases,
    tools,
    mode: str = "mock",
    llm_factory=None,
    budget_cents: float | None = None,
) -> dict:
    """Lance chaque approche sur chaque cas, agrège les métriques.

    mode="mock" : LLM fake déterministe (gratuit). mode="live" : vrai LLM via
    llm_factory ; budget_cents bloque l'exécution dès que le cumul dépasse le
    budget (D62) — results["budget_exceeded"] est alors true.
    """
    per_approach: dict[str, list[dict]] = {}
    spent_cents = 0.0
    budget_exceeded = False
    live_llm = llm_factory() if (mode == "live" and llm_factory) else None
    for approach, run_case in APPROACHES:
        entries = []
        for case in cases:
            if budget_exceeded:
                break
            t0 = time.perf_counter()
            outcome = await run_case(
                approach,
                case.id,
                case.question,
                case.expected_tool,
                case.mock_tool_call,
                case.mock_final,
                tools,
                live_llm=live_llm,
            )
            spent_cents += outcome.cost_cents
            if budget_cents is not None and spent_cents > budget_cents:
                budget_exceeded = True
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
                guardrails=[
                    GuardrailDecision(check=check, ok=ok, detail="")
                    for check, ok in outcome.extra.get("guardrails", [])
                ],
            )
            metrics = compute_metrics(agent_result, case.expected_tool)
            # Honnêteté : compute_metrics met True par défaut quand il n'y a pas de
            # garde-fous. Une approche sans garde-fous en code ne « réussit » pas
            # ces métriques : on les met à 0 et on compte guardrails_applied.
            if not outcome.extra.get("guardrails"):
                garde_fou_keys = (
                    "numbers_sourced",
                    "format_ok",
                    "language_ok",
                    "disclaimer_ok",
                )
                for key in garde_fou_keys:
                    metrics[key] = 0.0
                metrics["guardrails_applied"] = 0.0
            else:
                metrics["guardrails_applied"] = 1.0
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
        if n == 0:
            # Approche arrêtée par le budget avant le moindre cas.
            summary[approach] = {"cases": 0, "stopped_by_budget": True}
            continue
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
                    "format_ok",
                    "language_ok",
                    "disclaimer_ok",
                    "guardrails_applied",
                )
            },
        }
    return {
        "mode": mode,
        "cases": [c.id for c in cases],
        "per_approach": per_approach,
        "summary": summary,
        "spent_cents": round(spent_cents, 3),
        "budget_cents": budget_cents,
        "budget_exceeded": budget_exceeded,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="runs LLM réels via LiteLLM (vraies clés requises, D62)",
    )
    parser.add_argument(
        "--budget-eur",
        type=float,
        default=2.0,
        help="budget max en € pour le mode live, bloqué en code (défaut 2, D62)",
    )
    args = parser.parse_args()
    cases = load_cases(CASES_PATH)
    tools = build_tools(MockMarket())
    if args.live:
        from investia.config import get_settings
        from investia.llm import build_llm_client

        settings = get_settings()
        if not (settings.openrouter_api_key or settings.mistral_api_key):
            raise SystemExit("mode --live : aucune clé LLM (voir .env.example)")
        llm_factory = lambda: build_llm_client(settings)  # noqa: E731
        results = await run_all(
            cases,
            tools,
            mode="live",
            llm_factory=llm_factory,
            budget_cents=args.budget_eur * 100,
        )
        out = RESULTS_PATH.with_name("results-live.json")
    else:
        results = await run_all(cases, tools, mode="mock")
        out = RESULTS_PATH
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results["summary"], indent=2, ensure_ascii=False))
    if results["mode"] == "live":
        print(
            f"\ncoût total : {results['spent_cents']} cts · "
            f"budget dépassé : {results['budget_exceeded']}"
        )
    print(f"\n→ {out}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
