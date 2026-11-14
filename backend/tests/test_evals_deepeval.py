"""Tests du bridge DeepEval (spec 14a) — écrits AVANT evals/deepeval_bridge.py.

Déterministes, zéro réseau : ToolCorrectnessMetric ne fait pas appel au LLM
(la clé OPENAI_API_KEY bidon ne sert qu'au constructeur de deepeval).
"""

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")  # constructeur deepeval, aucun appel

from investia.agent import run_agent
from investia.agent.loop import AgentResult, ToolCallLog
from investia.evals.deepeval_bridge import deepeval_tool_correctness, to_llm_test_case
from investia.evals.runner import (
    FakePdfReader,
    FakePythonSandbox,
    FakeWebSearcher,
    MockLlm,
    MockMarket,
    load_cases,
)
from investia.tools import build_tools

CASES = [
    c
    for c in load_cases()
    if c.expected_tool
    and c.consistency_k == 1
    and c.mock_router_neighbors is None
    and c.mock_cache_hit is None
    and not c.multi_agent
    and c.mock_agent_router_neighbors is None
]


async def _run_case(case):
    tools = build_tools(
        MockMarket(),
        web_searcher=FakeWebSearcher(),
        pdf_reader=FakePdfReader(),
        python_sandbox=FakePythonSandbox(),
    )
    reasoning = case.reasoning or ("plan" if case.mock_plan else "none")
    return await run_agent(case.question, MockLlm(case), tools, reasoning=reasoning)


async def test_cas_avec_expected_tool_scorent_1_en_deepeval():
    assert CASES, "au moins un cas avec expected_tool dans cases.yaml"
    for case in CASES:
        result = await _run_case(case)
        assert deepeval_tool_correctness(case, result) == 1.0, case.id


def test_mauvais_outil_score_0():
    case = CASES[0]
    fake = AgentResult(
        answer="x",
        turns=1,
        tool_calls=[ToolCallLog(tool="get_news", arguments={}, ok=True)],
    )
    assert deepeval_tool_correctness(case, fake) == 0.0


def test_to_llm_test_case_rempli_les_champs():
    case = CASES[0]
    result = AgentResult(
        answer="réponse",
        turns=1,
        tool_calls=[
            ToolCallLog(
                tool=case.expected_tool or "", arguments={"symbol": "AAPL"}, ok=True
            )
        ],
    )
    test_case = to_llm_test_case(case, result)
    assert test_case.input == case.question
    assert test_case.actual_output == "réponse"
    assert [t.name for t in test_case.tools_called] == [case.expected_tool]
    assert [t.name for t in test_case.expected_tools] == [case.expected_tool]
