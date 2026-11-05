"""Runner d'evals : exécute le jeu de cas sur l'agent (mock déterministe) et score."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from investia.agent import run_agent
from investia.evals.metrics import compute_metrics
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData, MarketDataService
from investia.tools import build_tools

EVALS_DIR = Path(__file__).resolve().parents[4] / "evals"
DEFAULT_CASES = EVALS_DIR / "cases.yaml"


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_tool: str | None
    mock_tool_call: dict[str, Any] | None
    mock_final: str


def load_cases(path: Path | None = None) -> list[EvalCase]:
    data = yaml.safe_load((path or DEFAULT_CASES).read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=c["id"],
            question=c["question"],
            expected_tool=c.get("expected_tool"),
            mock_tool_call=c.get("mock_tool_call"),
            mock_final=c["mock_final"],
        )
        for c in data["cases"]
    ]


class MockLlm:
    """LLM déterministe : rejoue le tool_call puis la réponse finale du cas."""

    def __init__(self, case: EvalCase):
        responses = []
        if case.mock_tool_call:
            responses.append(
                LlmResponse(
                    content="",
                    model="mock",
                    prompt_tokens=10,
                    completion_tokens=5,
                    cost_cents=0.01,
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name=case.mock_tool_call["name"],
                            arguments=case.mock_tool_call.get("arguments", {}),
                        )
                    ],
                )
            )
        responses.append(
            LlmResponse(
                content=case.mock_final,
                model="mock",
                prompt_tokens=10,
                completion_tokens=5,
                cost_cents=0.01,
            )
        )
        self._responses = responses

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class MockMarket:
    """Marché fake déterministe : zéro réseau pendant les evals."""

    async def get_quote(self, symbol: str) -> MarketData:
        return MarketData(
            value=344.63,
            currency="USD",
            source="mock",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol: str, days: int = 30):
        return []

    async def get_news(self, symbol: str, limit: int = 5):
        return []


async def run_evals(
    cases: list[EvalCase],
    market: MarketDataService | None = None,
    eval_store=None,
    mode: str = "mock",
    portfolio_service=None,
) -> dict[str, Any]:
    """Lance tous les cas, calcule les métriques, enregistre si eval_store fourni."""
    market = market or MockMarket()
    tools = build_tools(market, portfolio_service=portfolio_service)
    run_id = None
    if eval_store is not None:
        run_id = await eval_store.start_eval_run(
            model="mock" if mode == "mock" else "live", mode=mode
        )
    results = []
    for case in cases:
        llm = MockLlm(case)
        agent_result = await run_agent(case.question, llm, tools)
        metrics = compute_metrics(agent_result, case.expected_tool)
        entry = {"case_id": case.id, "metrics": metrics, "status": "ok"}
        if eval_store is not None and run_id is not None:
            for metric, score in metrics.items():
                await eval_store.log_result(run_id, case.id, metric, score)
        results.append(entry)
    return {"run_id": run_id, "mode": mode, "results": results}
