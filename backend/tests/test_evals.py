"""Tests du runner d'evals (métriques en code, mock déterministe, zéro réseau)."""

from datetime import UTC, datetime

from investia.agent import run_agent
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
