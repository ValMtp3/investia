"""Tests TDD de la brique 12a : plan-and-execute (reasoning.py + boucle + evals)."""

import json
from typing import Any

from investia.agent.reasoning import Plan, PlanStep, make_plan, parse_plan
from investia.llm.client import LlmResponse

TOOLS = ["get_quote", "get_news", "get_history", "get_indicators", "get_portfolio"]

PLAN_JSON = json.dumps(
    {
        "steps": [
            {"step": "récupérer le prix de AAPL", "tool": "get_quote"},
            {"step": "rédiger la réponse", "tool": None},
        ]
    }
)


class FakeLlm:
    """LLM fake : rejoue une liste de réponses, mémorise les appels."""

    def __init__(self, responses: list[LlmResponse]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        self.calls.append(
            {"model": model_key, "messages": list(messages), "tools": tools}
        )
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def make_response(content="", tool_calls=None, cost=0.01):
    from investia.llm.client import ToolCall

    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


# --- Task 1 : parse_plan / make_plan ---


def test_parse_plan_valid_json():
    plan = parse_plan(PLAN_JSON, TOOLS)
    assert plan.steps == [
        PlanStep(step="récupérer le prix de AAPL", tool="get_quote"),
        PlanStep(step="rédiger la réponse", tool=None),
    ]


def test_parse_plan_invalid_json_returns_empty_plan():
    assert parse_plan("pas du json", TOOLS).steps == []
    assert parse_plan("", TOOLS).steps == []


def test_parse_plan_tool_inconnu_devient_none():
    plan = parse_plan('{"steps": [{"step": "x", "tool": "tool_inconnu"}]}', TOOLS)
    assert plan.steps[0].tool is None


def test_parse_plan_json_entoure_de_texte():
    text = f"Voici le plan :\n```json\n{PLAN_JSON}\n```\nBonne analyse."
    plan = parse_plan(text, TOOLS)
    assert len(plan.steps) == 2


async def test_make_plan_calls_llm_once_and_returns_cost():
    llm = FakeLlm([make_response(content=PLAN_JSON, cost=0.02)])
    plan, cost = await make_plan(llm, "gpt-6-luna", "Quel est le prix de AAPL ?", TOOLS)
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["model"] == "gpt-6-luna"
    assert cost == 0.02
    assert plan.steps[0].tool == "get_quote"
    assert plan.steps[1].tool is None


async def test_make_plan_invalid_llm_output_returns_empty_plan():
    llm = FakeLlm([make_response(content="je ne sais pas", cost=0.01)])
    plan, cost = await make_plan(llm, "gpt-6-luna", "question", TOOLS)
    assert plan.steps == []
    assert cost == 0.01
