"""Raisonnement structuré de l'agent (étape 12a) : plan-and-execute.

Le plan est produit par un appel LLM dédié en début de run (JSON), puis parsé
en douceur : un plan illisible donne un plan vide, jamais d'exception.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from investia.agent.loop import LlmChat


@dataclass(frozen=True)
class PlanStep:
    step: str
    tool: str | None


@dataclass(frozen=True)
class Plan:
    steps: list[PlanStep] = field(default_factory=list)


@dataclass(frozen=True)
class ReflectionDecision:
    """Résultat d'une passe d'auto-critique (étape 12b)."""

    ok: bool
    problemes: list[str] = field(default_factory=list)


def parse_plan(text: str, tool_names: Collection[str] | None = None) -> Plan:
    """Parse le JSON du plan. Toute erreur -> plan vide (dégradé propre).

    Le JSON peut être entouré de texte (ex. bloc ```json ... ```) : on extrait
    le premier « { » .. dernier « } ». Un outil hors de `tool_names` devient None.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return Plan()
    try:
        data: Any = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return Plan()
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        return Plan()
    steps: list[PlanStep] = []
    for raw in data["steps"]:
        if not isinstance(raw, dict):
            continue
        step = str(raw.get("step", "")).strip()
        tool = raw.get("tool")
        if not isinstance(tool, str) or (tool_names is not None and tool not in tool_names):
            tool = None
        if step:
            steps.append(PlanStep(step=step, tool=tool))
    return Plan(steps=steps)


async def make_plan(
    llm: LlmChat, model_key: str, question: str, tool_names: list[str]
) -> tuple[Plan, float]:
    """Appel LLM dédié : produit le plan JSON. Retourne (plan, coût en centimes)."""
    from investia.agent.prompts import PLAN_PROMPT

    messages = [
        {"role": "system", "content": PLAN_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question de l'utilisateur : {question}\n"
                f"Outils disponibles : {', '.join(tool_names)}"
            ),
        },
    ]
    response = await llm.chat(model_key, messages, tools=None)
    return parse_plan(response.content, tool_names), response.cost_cents


MAX_REFLECT_OUTPUT_CHARS = 4000


def parse_reflection(text: str) -> ReflectionDecision:
    """Parse la critique JSON. Illisible -> ok=True (les garde-fous en code décident)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return ReflectionDecision(ok=True)
    try:
        data: Any = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return ReflectionDecision(ok=True)
    if not isinstance(data, dict):
        return ReflectionDecision(ok=True)
    problemes = data.get("problemes")
    return ReflectionDecision(
        ok=bool(data.get("ok", True)),
        problemes=[str(p) for p in problemes if isinstance(problemes, list)],
    )


async def reflect(
    llm: LlmChat, model_key: str, answer: str, tool_outputs: list[str]
) -> tuple[ReflectionDecision, float]:
    """Passe d'auto-critique : un appel LLM dédié juge la réponse candidate.

    Les sorties d'outils sont tronquées (MAX_REFLECT_OUTPUT_CHARS au total).
    Retourne (décision, coût en centimes). La réflexion ne bloque jamais seule :
    en cas de doute, ok=True et les garde-fous en code tranchent.
    """
    from investia.agent.prompts import REFLECT_PROMPT

    # Chaque sortie est tronquée à parts égales : le total tient dans la limite
    # et chaque outil reste représenté dans le contexte de relecture.
    per_output = MAX_REFLECT_OUTPUT_CHARS // max(1, len(tool_outputs))
    truncated = [
        output[:per_output] + ("...[tronqué]" if len(output) > per_output else "")
        for output in tool_outputs
    ]
    joined = "\n".join(truncated)
    messages = [
        {"role": "system", "content": REFLECT_PROMPT},
        {
            "role": "user",
            "content": (
                f"Réponse candidate de l'agent :\n{answer}\n\n"
                f"Sorties de ses outils :\n{joined}"
            ),
        },
    ]
    response = await llm.chat(model_key, messages, tools=None)
    return parse_reflection(response.content), response.cost_cents
