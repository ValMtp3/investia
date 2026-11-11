"""Tests TDD de la brique 12d : garde-fous LLM en renfort (elephant-1 + logprobs)."""

from typing import Any

import pytest

from investia.guardrails.llm_check import (
    MIN_CONFIDENCE,
    NON_BLOCK_THRESHOLD,
    UNSAFE_BLOCK_THRESHOLD,
    check_safety_llm,
    check_safety_logprobs,
)
from investia.llm.client import LlmResponse
from investia.llm.decisions import DecisionAnswer


def decision(value, probabilities, confidence):
    async def decide(state, questions):
        return {
            "safety": DecisionAnswer(
                value=value, probabilities=probabilities, confidence=confidence
            )
        }

    return decide


# --- check_safety_llm (elephant-1) ---


async def test_safety_llm_bloque_si_unsafe_confiant():
    result = await check_safety_llm(
        "ça va monter", decision("unsafe", {"unsafe": 0.9, "safe": 0.1}, 0.95)
    )
    assert result.ok is False
    assert "unsafe=0.90" in result.detail


async def test_safety_llm_passe_si_confiance_basse():
    result = await check_safety_llm(
        "ça va monter", decision("unsafe", {"unsafe": 0.9, "safe": 0.1}, 0.3)
    )
    assert result.ok is True
    assert f"confiance={0.3:.2f}" in result.detail


async def test_safety_llm_passe_si_safe():
    result = await check_safety_llm(
        "analyse neutre", decision("safe", {"safe": 0.95, "unsafe": 0.05}, 0.9)
    )
    assert result.ok is True


async def test_safety_llm_erreur_indisponible_ne_bloque_pas():
    async def decide_ko(state, questions):
        raise RuntimeError("gateway down")

    result = await check_safety_llm("réponse", decide_ko)
    assert result.ok is True
    assert "indisponible" in result.detail


async def test_safety_llm_sans_reponse_indisponible():
    async def decide_vide(state, questions):
        return {}

    result = await check_safety_llm("réponse", decide_vide)
    assert result.ok is True
    assert "indisponible" in result.detail


# --- check_safety_logprobs (LLM-as-Jev) ---


class LogprobsLlm:
    """LLM fake qui rend first_token_logprobs quand on demande logprobs=True."""

    def __init__(self, logprobs: dict[str, float] | None):
        self._logprobs = logprobs
        self.calls: list[dict[str, Any]] = []

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        self.calls.append(
            {
                "model": model_key,
                "messages": list(messages),
                "tools": tools,
                "logprobs": logprobs,
                "temperature": temperature,
            }
        )
        return LlmResponse(
            content="Non" if self._logprobs else "Oui",
            model="mock",
            prompt_tokens=10,
            completion_tokens=1,
            cost_cents=0.01,
            first_token_logprobs=self._logprobs if logprobs else None,
        )


async def test_safety_logprobs_bloque_si_non_probable():
    llm = LogprobsLlm({"Non": 0.98, "Oui": 0.02})
    result = await check_safety_logprobs("ça va monter", llm, "small")
    assert result.ok is False
    assert "P(non)=0.98" in result.detail
    assert llm.calls[0]["logprobs"] is True
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["temperature"] == 0.0


async def test_safety_logprobs_passe_si_oui_probable():
    llm = LogprobsLlm({"Oui": 0.9, "Non": 0.1})
    result = await check_safety_logprobs("analyse neutre", llm, "small")
    assert result.ok is True


async def test_safety_logprobs_sans_logprobs_indisponible():
    llm = LogprobsLlm(None)
    result = await check_safety_logprobs("réponse", llm, "small")
    assert result.ok is True
    assert "indisponible" in result.detail


def test_seuils_sont_coherents():
    assert UNSAFE_BLOCK_THRESHOLD == 0.7
    assert MIN_CONFIDENCE == 0.6
    assert NON_BLOCK_THRESHOLD == 0.7
