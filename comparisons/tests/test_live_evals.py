"""TDD 8 (live) : le budget des evals réelles est bloqué en code (D62).

Contrat : run_evals --live --budget-eur 2 s'arrête dès que le cumul des coûts
dépasse le budget, et le note dans results-live.json (budget_exceeded: true).
"""

from pathlib import Path

from investia.evals.runner import MockMarket, load_cases
from investia.tools import build_tools

import run_evals

CASES = load_cases(Path(__file__).resolve().parents[2] / "evals" / "cases.yaml")
TOOLS = build_tools(MockMarket())


class CostlyLlm:
    """LLM fake qui coûte cher à chaque appel : déclenche le dépassement de budget."""

    def __init__(self, cost_cents: float):
        self.cost_cents = cost_cents

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        from investia.llm.client import LlmResponse

        return LlmResponse(
            content="## Thèse\nok\n\n## Risques\naucun\n\n## Confiance\n50\n\n"
            "## Sources\n- mock\n\nSimulation — pas un conseil en investissement.",
            model="live-fake",
            prompt_tokens=100,
            completion_tokens=50,
            cost_cents=self.cost_cents,
        )


async def test_live_stops_at_budget_and_marks_it():
    # 2 € = 200 cts ; chaque appel coûte 100 cts → après 2 cas le budget est dépassé
    results = await run_evals.run_all(
        CASES,
        TOOLS,
        mode="live",
        llm_factory=lambda: CostlyLlm(100.0),
        budget_cents=200,
    )
    assert results["mode"] == "live"
    assert results["budget_exceeded"] is True
    assert results["spent_cents"] > 200
    # pas tous les cas × approches ont tourné : arrêt au budget
    total = sum(len(v) for v in results["per_approach"].values())
    assert total < len(CASES) * len(results["per_approach"])


async def test_live_within_budget_marks_not_exceeded():
    results = await run_evals.run_all(
        CASES[:1],
        TOOLS,
        mode="live",
        llm_factory=lambda: CostlyLlm(1.0),
        budget_cents=10_000,
    )
    assert results["budget_exceeded"] is False
    assert results["spent_cents"] <= 10_000
