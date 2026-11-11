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
