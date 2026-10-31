"""La boucle d'agent : réfléchir -> appeler un outil -> lire le résultat -> recommencer.

Écrite à la main (D41), zéro framework. Max N tours + budget par run : dépassement
-> arrêt propre, jamais de boucle infinie.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from investia.llm.client import LlmResponse
from investia.llm.router import choose
from investia.tools.base import BaseTool, ToolError


class LlmChat(Protocol):
    """Ce dont la boucle a besoin côté LLM (implémenté par LlmClient)."""

    async def chat(
        self,
        model_key: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse: ...


@dataclass(frozen=True)
class ToolCallLog:
    tool: str
    arguments: dict[str, Any]
    ok: bool


@dataclass(frozen=True)
class AgentResult:
    answer: str
    turns: int
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    total_cost_cents: float = 0.0
    model: str = ""


DEFAULT_MAX_TURNS = 8


async def run_agent(
    question: str,
    llm: LlmChat,
    tools: dict[str, BaseTool],
    max_turns: int = DEFAULT_MAX_TURNS,
    model_key: str | None = None,
) -> AgentResult:
    """Exécute la boucle d'agent sur une question. Arrêt propre si max tours atteint."""
    from investia.agent.prompts import SYSTEM_PROMPT

    model_key = model_key or choose(question)
    tool_specs = [tool.to_openai_tool() for tool in tools.values()]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    log: list[ToolCallLog] = []
    total_cost = 0.0

    for turn in range(1, max_turns + 1):
        response = await llm.chat(model_key, messages, tools=tool_specs)
        total_cost += response.cost_cents
        if not response.tool_calls:
            return AgentResult(
                answer=response.content,
                turns=turn,
                tool_calls=log,
                total_cost_cents=total_cost,
                model=response.model,
            )
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in response.tool_calls
                ],
            }
        )
        for call in response.tool_calls:
            result_text = await _execute_tool(tools, call.name, call.arguments)
            log.append(
                ToolCallLog(
                    tool=call.name,
                    arguments=call.arguments,
                    ok=not result_text.startswith("erreur"),
                )
            )
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result_text}
            )

    return AgentResult(
        answer=(
            f"[arrêt après {max_turns} tours — budget de tours atteint] "
            "La question semble demander trop d'étapes."
        ),
        turns=max_turns,
        tool_calls=log,
        total_cost_cents=total_cost,
        model=model_key,
    )


async def _execute_tool(
    tools: dict[str, BaseTool], name: str, arguments: dict[str, Any]
) -> str:
    """Exécute un outil ; toute erreur est renvoyée au modèle sous forme lisible."""
    tool = tools.get(name)
    if tool is None:
        return f"erreur: outil inconnu {name!r}"
    try:
        args = tool.args_schema.model_validate(arguments)
        result = await tool.run(args)
    except ValidationError as error:
        return f"erreur: arguments invalides pour {name} — {error.errors()[0]['msg']}"
    except ToolError as error:
        return f"erreur: {error}"
    return json.dumps(result, default=str, ensure_ascii=False)
