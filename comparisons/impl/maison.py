"""Implémentation de référence : le harness maison (investia.agent.run_agent)."""

import time
from typing import Any

from investia.agent import run_agent
from investia.evals.runner import EvalCase, MockLlm

from impl.base import CaseOutcome


async def run_case(
    approach: str,
    case_id: str,
    question: str,
    expected_tool: str,
    mock_tool_call: dict[str, Any],
    mock_final: str,
    tools: dict[str, Any],
) -> CaseOutcome:
    case = EvalCase(
        id=case_id,
        question=question,
        expected_tool=expected_tool,
        mock_tool_call=mock_tool_call,
        mock_final=mock_final,
    )
    llm = MockLlm(case)
    t0 = time.perf_counter()
    result = await run_agent(question, llm, tools)
    duration_ms = (time.perf_counter() - t0) * 1000
    tool_called = result.tool_calls[0].tool if result.tool_calls else None
    return CaseOutcome(
        approach=approach,
        case_id=case_id,
        answer=result.answer,
        tool_called=tool_called,
        tool_ok=tool_called == expected_tool,
        cost_cents=result.total_cost_cents,
        duration_ms=duration_ms,
        extra={
            "guardrails": [(g.check, g.ok) for g in result.guardrails],
        },
    )
