"""La boucle d'agent : réfléchir -> appeler un outil -> lire le résultat -> recommencer.

Écrite à la main (D41), zéro framework. Max N tours + budget par run : dépassement
-> arrêt propre, jamais de boucle infinie.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from investia.guardrails import run_all_checks
from investia.llm.client import LlmResponse
from investia.llm.router import choose
from investia.tools.base import BaseTool, ToolError
from investia.tracing.store import TraceStoreProtocol


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
class GuardrailDecision:
    check: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class AgentResult:
    answer: str
    turns: int
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    total_cost_cents: float = 0.0
    model: str = ""
    guardrails: list[GuardrailDecision] = field(default_factory=list)


DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_CORRECTIONS = 2


async def run_agent(
    question: str,
    llm: LlmChat,
    tools: dict[str, BaseTool],
    max_turns: int = DEFAULT_MAX_TURNS,
    model_key: str | None = None,
    max_corrections: int = DEFAULT_MAX_CORRECTIONS,
    trace_store: TraceStoreProtocol | None = None,
    event_sink: Any | None = None,
) -> AgentResult:
    """Boucle d'agent + garde-fous. Arrêt propre si max tours/corrections atteints."""
    from investia.agent.prompts import SYSTEM_PROMPT

    model_key = model_key or choose(question)
    store = trace_store
    run_id = await store.start_run(question) if store is not None else None

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            await event_sink(kind, payload)

    await emit(
        "start", {"question": question, "max_turns": max_turns, "run_id": run_id}
    )
    tool_specs = [tool.to_openai_tool() for tool in tools.values()]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    log: list[ToolCallLog] = []
    guardrails: list[GuardrailDecision] = []
    total_cost = 0.0
    corrections = 0

    for turn in range(1, max_turns + 1):
        response = await llm.chat(model_key, messages, tools=tool_specs)
        total_cost += response.cost_cents
        if store is not None and run_id is not None:
            await store.log_step(
                run_id,
                turn,
                "llm_call",
                {
                    "model": response.model,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "cost_cents": response.cost_cents,
                    "tool_calls": [call.name for call in response.tool_calls],
                },
            )
        await emit(
            "llm_call",
            {
                "turn": turn,
                "model": response.model,
                "cost_cents": response.cost_cents,
                "tool_calls": [c.name for c in response.tool_calls],
            },
        )
        if response.tool_calls:
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
                entry = ToolCallLog(
                    tool=call.name,
                    arguments=call.arguments,
                    ok=not result_text.startswith("erreur"),
                )
                log.append(entry)
                if store is not None and run_id is not None:
                    await store.log_step(
                        run_id,
                        turn,
                        "tool_call",
                        {
                            "name": call.name,
                            "arguments": call.arguments,
                            "ok": entry.ok,
                            "result": result_text,
                        },
                    )
                await emit(
                    "tool_call",
                    {
                        "turn": turn,
                        "name": call.name,
                        "arguments": call.arguments,
                        "ok": entry.ok,
                    },
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result_text}
                )
            continue

        # Réponse finale : les garde-fous vérifient en code avant validation.
        tool_outputs = [m["content"] for m in messages if m.get("role") == "tool"]
        checks = run_all_checks(response.content, tool_outputs)
        guardrails.extend(
            GuardrailDecision(check=name, ok=result.ok, detail=result.detail)
            for name, result in checks
        )
        for name, result in checks:
            await emit(
                "guardrail",
                {"turn": turn, "check": name, "ok": result.ok, "detail": result.detail},
            )
        if store is not None and run_id is not None:
            for name, result in checks:
                await store.log_step(
                    run_id,
                    turn,
                    "guardrail",
                    {"check": name, "ok": result.ok, "detail": result.detail},
                )
        failed = [(name, result.detail) for name, result in checks if not result.ok]
        if not failed:
            await emit("answer", {"turn": turn, "text": response.content})
            result = AgentResult(
                answer=response.content,
                turns=turn,
                tool_calls=log,
                total_cost_cents=total_cost,
                model=response.model,
                guardrails=guardrails,
            )
            if store is not None and run_id is not None:
                await store.finish_run(
                    run_id,
                    answer=result.answer,
                    model=result.model,
                    turns=result.turns,
                    cost_cents=result.total_cost_cents,
                    status="ok",
                )
            await emit("answer", {"turn": turn, "text": result.answer})
            await emit(
                "done",
                {
                    "turns": result.turns,
                    "cost_cents": result.total_cost_cents,
                    "status": "ok",
                },
            )
            return result
        if corrections < max_corrections:
            corrections += 1
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Garde-fou : ta réponse est bloquée ("
                        + "; ".join(f"{name}: {detail}" for name, detail in failed)
                        + "). Corrige-la et réponds à nouveau en respectant le format."
                    ),
                }
            )
            continue
        blocked_answer = (
            "[réponse bloquée par les garde-fous après "
            f"{max_corrections} corrections : "
            + "; ".join(f"{name}: {detail}" for name, detail in failed)
            + "]"
        )
        result = AgentResult(
            answer=blocked_answer,
            turns=turn,
            tool_calls=log,
            total_cost_cents=total_cost,
            model=response.model,
            guardrails=guardrails,
        )
        if store is not None and run_id is not None:
            await store.finish_run(
                run_id,
                answer=result.answer,
                model=result.model,
                turns=result.turns,
                cost_cents=result.total_cost_cents,
                status="blocked",
            )
        await emit("answer", {"turn": turn, "text": result.answer})
        await emit(
            "done",
            {
                "turns": result.turns,
                "cost_cents": result.total_cost_cents,
                "status": "blocked",
            },
        )
        return result

    max_turns_answer = (
        f"[arrêt après {max_turns} tours — budget de tours atteint] "
        "La question semble demander trop d'étapes."
    )
    result = AgentResult(
        answer=max_turns_answer,
        turns=max_turns,
        tool_calls=log,
        total_cost_cents=total_cost,
        model=model_key,
        guardrails=guardrails,
    )
    if store is not None and run_id is not None:
        await store.finish_run(
            run_id,
            answer=result.answer,
            model=result.model,
            turns=result.turns,
            cost_cents=result.total_cost_cents,
            status="max_turns",
        )
    await emit("answer", {"turn": max_turns, "text": result.answer})
    await emit(
        "done",
        {
            "turns": result.turns,
            "cost_cents": result.total_cost_cents,
            "status": "max_turns",
        },
    )
    return result


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
