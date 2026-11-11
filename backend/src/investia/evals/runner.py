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
    mock_plan: str | None = None  # étape 12a : plan JSON rejoué avant le tool_call
    # étape 12b : séquence ordonnée de réponses (dict {"tool_call": {...}} ou string content)
    mock_responses: list[Any] | None = None
    reasoning: str | None = None  # mode de raisonnement passé à run_agent
    # étape 12c : self-consistency — k variantes de séquences, une par sous-run
    consistency_k: int = 1
    mock_variants: list[list[Any]] | None = None
    # étape 12d : garde-fous LLM — réponse mockée du modèle de décision / des logprobs
    mock_decision: dict[str, Any] | None = None
    mock_logprobs: dict[str, float] | None = None
    # étape 12e : cache sémantique — réponse servie par le cache sans appel LLM
    mock_cache_hit: str | None = None


def load_cases(path: Path | None = None) -> list[EvalCase]:
    data = yaml.safe_load((path or DEFAULT_CASES).read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=c["id"],
            question=c["question"],
            expected_tool=c.get("expected_tool"),
            mock_tool_call=c.get("mock_tool_call"),
            mock_final=c.get("mock_final", ""),
            mock_plan=c.get("mock_plan"),
            mock_responses=c.get("mock_responses"),
            reasoning=c.get("reasoning"),
            consistency_k=int(c.get("consistency_k", 1)),
            mock_variants=c.get("mock_variants"),
            mock_decision=c.get("mock_decision"),
            mock_logprobs=c.get("mock_logprobs"),
            mock_cache_hit=c.get("mock_cache_hit"),
        )
        for c in data["cases"]
    ]


class FakeSemanticCache:
    """Cache sémantique déterministe (étape 12e) : rend mock_cache_hit au lookup."""

    def __init__(self, case: EvalCase):
        self._case = case
        self.stored: list[tuple[str, str]] = []

    async def lookup(self, question: str) -> str | None:
        return self._case.mock_cache_hit

    async def store(self, question: str, answer: str) -> None:
        self.stored.append((question, answer))


class FakeDecisionClient:
    """Client de décision déterministe (étape 12d) : rejoue mock_decision."""

    def __init__(self, case: EvalCase):
        self._case = case

    async def decide(self, state, questions):
        from investia.llm.decisions import DecisionAnswer

        d = self._case.mock_decision or {}
        return {
            "safety": DecisionAnswer(
                value=d.get("value"),
                probabilities={k: float(v) for k, v in d.get("probabilities", {}).items()},
                confidence=float(d.get("confidence", 0.0)),
            )
        }


def _mock_response(content: str = "", tool_call: dict[str, Any] | None = None) -> LlmResponse:
    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=0.01,
        tool_calls=[
            ToolCall(
                id="call_1",
                name=tool_call["name"],
                arguments=tool_call.get("arguments", {}),
            )
        ]
        if tool_call
        else [],
    )


class MockLlm:
    """LLM déterministe : rejoue le plan (12a), le tool_call puis la réponse finale.

    Avec `mock_responses` (12b), rejoue la séquence ordonnée fournie.
    """

    def __init__(self, case: EvalCase):
        self._case = case
        if case.mock_responses:
            self._responses = [
                _mock_response(tool_call=item["tool_call"])
                if isinstance(item, dict) and "tool_call" in item
                else _mock_response(
                    content=item["content"] if isinstance(item, dict) else str(item)
                )
                for item in case.mock_responses
            ]
            return
        responses = []
        if case.mock_plan:
            responses.append(_mock_response(content=case.mock_plan))
        if case.mock_tool_call:
            responses.append(_mock_response(tool_call=case.mock_tool_call))
        responses.append(_mock_response(content=case.mock_final))
        self._responses = responses

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        if logprobs and self._case.mock_logprobs is not None:
            return LlmResponse(
                content="Non",
                model="mock",
                prompt_tokens=10,
                completion_tokens=1,
                cost_cents=0.01,
                first_token_logprobs=self._case.mock_logprobs,
            )
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
        reasoning = case.reasoning or ("plan" if case.mock_plan else "none")
        llm_factory = None
        variants = case.mock_variants
        if case.consistency_k > 1 and variants:

            def llm_factory(i: int, case: EvalCase = case, variants: list = variants) -> MockLlm:
                variant = EvalCase(
                    id=f"{case.id}#{i}",
                    question=case.question,
                    expected_tool=None,
                    mock_tool_call=None,
                    mock_final="",
                    mock_responses=variants[i],
                )
                return MockLlm(variant)

        agent_result = await run_agent(
            case.question,
            MockLlm(case),
            tools,
            reasoning=reasoning,
            consistency_k=case.consistency_k,
            llm_factory=llm_factory,
            decision_client=FakeDecisionClient(case) if case.mock_decision else None,
            logprobs_guardrail=bool(case.mock_logprobs),
            semantic_cache=FakeSemanticCache(case) if case.mock_cache_hit else None,
        )
        metrics = compute_metrics(agent_result, case.expected_tool)
        entry = {"case_id": case.id, "metrics": metrics, "status": agent_result.status}
        if eval_store is not None and run_id is not None:
            for metric, score in metrics.items():
                await eval_store.log_result(run_id, case.id, metric, score)
        results.append(entry)
    return {"run_id": run_id, "mode": mode, "results": results}
