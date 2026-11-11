"""Tests TDD de la brique 12b : réflexion/auto-critique (reflect + boucle + evals)."""

import json
from typing import Any

import pytest

from investia.agent import run_agent
from investia.agent.reasoning import (
    Plan,
    PlanStep,
    ReflectionDecision,
    make_plan,
    parse_reflection,
    reflect,
)
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools
from datetime import UTC, datetime


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
    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


# --- Task 1 : parse_reflection / reflect ---


def test_parse_reflection_valid_ko():
    decision = parse_reflection('{"ok": false, "problemes": ["chiffre non sourcé"]}')
    assert decision.ok is False
    assert decision.problemes == ["chiffre non sourcé"]


def test_parse_reflection_valid_ok():
    decision = parse_reflection('{"ok": true, "problemes": []}')
    assert decision.ok is True
    assert decision.problemes == []


def test_parse_reflection_invalid_returns_ok_true():
    # Dégradé propre : illisible -> on laisse les garde-fous en code décider.
    decision = parse_reflection("pas du json")
    assert decision.ok is True
    assert decision.problemes == []


async def test_reflect_calls_llm_once_truncates_outputs_and_returns_cost():
    llm = FakeLlm([make_response(content='{"ok": true, "problemes": []}', cost=0.02)])
    big_output = "x" * 10_000
    decision, cost = await reflect(
        llm, "gpt-6-luna", "ma réponse", [big_output, "petite sortie"]
    )
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] is None
    sent = json.dumps(llm.calls[0]["messages"])
    assert len(sent) < 6000  # la grosse sortie a été tronquée
    assert "petite sortie" in sent
    assert decision.ok is True
    assert cost == 0.02
