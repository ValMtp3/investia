"""Tests du runner d'evals (métriques en code, mock déterministe, zéro réseau)."""

import json
from datetime import UTC, datetime

from investia.agent import AgentResult, run_agent
from investia.agent.loop import ToolCallLog
from investia.agent.reasoning import Plan, PlanStep
from investia.evals.metrics import compute_metrics
from investia.evals.runner import EvalCase, MockLlm, load_cases, run_evals
from investia.market.base import MarketData

FINAL_OK = """## Thèse
Le prix est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


def make_case(case_id="prix-aapl", expected_tool="get_quote", final=FINAL_OK):
    return EvalCase(
        id=case_id,
        question="prix de AAPL ?",
        expected_tool=expected_tool,
        mock_tool_call={"name": "get_quote", "arguments": {"symbol": "AAPL"}},
        mock_final=final,
    )


async def test_metrics_tool_used_and_numbers_sourced():
    llm = MockLlm(make_case())
    from investia.tools import build_tools

    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    metrics = compute_metrics(result, expected_tool="get_quote")
    assert metrics["tool_used"] == 1.0
    assert metrics["numbers_sourced"] == 1.0
    assert metrics["format_ok"] == 1.0
    assert metrics["turns"] == 2.0


async def test_metrics_detect_wrong_tool_and_invented_number():
    case = make_case(expected_tool="get_news")  # mauvais outil attendu
    llm = MockLlm(case)
    from investia.tools import build_tools

    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    metrics = compute_metrics(result, expected_tool=case.expected_tool)
    assert metrics["tool_used"] == 0.0

    bad_final = FINAL_OK.replace("344.63", "999999")
    case_bad = make_case(final=bad_final)
    llm2 = MockLlm(case_bad)
    result2 = await run_agent(
        "prix ?", llm2, build_tools(FakeMarket()), max_corrections=0
    )
    metrics2 = compute_metrics(result2, expected_tool="get_quote")
    assert metrics2["numbers_sourced"] == 0.0


async def test_run_evals_returns_scores_for_every_case_and_metric():
    cases = [make_case("prix-aapl"), make_case("prix-btc", expected_tool="get_quote")]
    # le 2e cas attend le mauvais outil -> tool_used = 0
    cases[1] = make_case("prix-btc", expected_tool="get_news")
    summary = await run_evals(cases, market=FakeMarket(), mode="mock")
    assert len(summary["results"]) == 2
    first = summary["results"][0]
    assert first["case_id"] == "prix-aapl"
    assert first["metrics"]["tool_used"] == 1.0
    second = summary["results"][1]
    assert second["metrics"]["tool_used"] == 0.0


async def test_run_evals_passes_portfolio_service_to_build_tools(monkeypatch):
    """Spec 4.6 : le runner d'evals transmet le service portefeuille à build_tools."""
    import investia.evals.runner as runner

    captured: list[dict] = []
    real_build_tools = runner.build_tools

    def spy(market, **kwargs):
        captured.append(kwargs)
        return real_build_tools(market, **kwargs)

    monkeypatch.setattr(runner, "build_tools", spy)

    class FakePortfolioService:
        async def get_portfolio(self):
            return {"cash": 10_000.0, "positions": [], "currency": "EUR"}

    service = FakePortfolioService()
    await run_evals(
        [make_case()], market=FakeMarket(), mode="mock", portfolio_service=service
    )
    assert captured[-1]["portfolio_service"] is service

    await run_evals([make_case()], market=FakeMarket(), mode="mock")
    assert captured[-1]["portfolio_service"] is None


# --- Étape 12a : métrique plan_suivi ---


def test_plan_suivi_ok_quand_outils_dans_le_plan():
    result = AgentResult(
        answer="x",
        turns=2,
        tool_calls=[ToolCallLog(tool="get_quote", arguments={}, ok=True)],
        plan=Plan(steps=[PlanStep(step="prix AAPL", tool="get_quote")]),
    )
    assert compute_metrics(result, "get_quote")["plan_suivi"] == 1.0


def test_plan_suivi_zero_quand_outil_hors_plan():
    result = AgentResult(
        answer="x",
        turns=2,
        tool_calls=[ToolCallLog(tool="get_news", arguments={}, ok=True)],
        plan=Plan(steps=[PlanStep(step="prix AAPL", tool="get_quote")]),
    )
    assert compute_metrics(result, "get_news")["plan_suivi"] == 0.0


def test_plan_suivi_un_sans_plan_ou_plan_vide():
    sans_plan = AgentResult(answer="x", turns=1)
    assert compute_metrics(sans_plan, None)["plan_suivi"] == 1.0
    plan_vide = AgentResult(answer="x", turns=1, plan=Plan())
    assert compute_metrics(plan_vide, None)["plan_suivi"] == 1.0


def test_load_cases_from_yaml(tmp_path):
    yaml_content = """
cases:
  - id: prix-aapl
    question: "prix de AAPL ?"
    expected_tool: get_quote
    mock_tool_call: {name: get_quote, arguments: {symbol: AAPL}}
    mock_final: "réponse mock"
"""
    path = tmp_path / "cases.yaml"
    path.write_text(yaml_content)
    cases = load_cases(path)
    assert len(cases) == 1
    assert cases[0].id == "prix-aapl"
    assert cases[0].expected_tool == "get_quote"


# --- Étape 12a : cas d'evals avec mock_plan ---

FINAL_SANS_CHIFFRE = """## Thèse
Aucune actualité disponible pour l'instant (source : mock).

## Risques
volatilité.

## Confiance
60

## Sources
- mock

Simulation — pas un conseil en investissement.
"""


def test_load_cases_avec_mock_plan(tmp_path):
    yaml_content = """
cases:
  - id: plan-suivi
    question: "prix de AAPL ?"
    expected_tool: get_quote
    mock_plan: '{"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}'
    mock_tool_call: {name: get_quote, arguments: {symbol: AAPL}}
    mock_final: "réponse mock"
"""
    path = tmp_path / "cases.yaml"
    path.write_text(yaml_content)
    cases = load_cases(path)
    assert cases[0].mock_plan is not None
    assert "get_quote" in cases[0].mock_plan


async def test_run_evals_plan_suivi_et_non_suivi():
    case_suivi = EvalCase(
        id="plan-suivi",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_plan=json.dumps({"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}),
        mock_tool_call={"name": "get_quote", "arguments": {"symbol": "AAPL"}},
        mock_final=FINAL_OK,
    )
    case_non_suivi = EvalCase(
        id="plan-non-suivi",
        question="actus de AAPL ?",
        expected_tool="get_news",
        mock_plan=json.dumps({"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}),
        mock_tool_call={"name": "get_news", "arguments": {"symbol": "AAPL"}},
        mock_final=FINAL_SANS_CHIFFRE,
    )
    summary = await run_evals([case_suivi, case_non_suivi], market=FakeMarket(), mode="mock")
    by_id = {r["case_id"]: r["metrics"] for r in summary["results"]}
    assert by_id["plan-suivi"]["plan_suivi"] == 1.0
    assert by_id["plan-suivi"]["tool_used"] == 1.0
    assert by_id["plan-non-suivi"]["plan_suivi"] == 0.0
    assert by_id["plan-non-suivi"]["tool_used"] == 1.0
