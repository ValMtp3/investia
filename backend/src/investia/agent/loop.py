"""La boucle d'agent : réfléchir -> appeler un outil -> lire le résultat -> recommencer.

Écrite à la main (D41), zéro framework. Max N tours + budget par run : dépassement
-> arrêt propre, jamais de boucle infinie.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from investia.agent.approval import ApprovalRegistry
from investia.agent.reasoning import Plan, make_plan
from investia.guardrails import run_all_checks
from investia.llm.client import LlmResponse
from investia.llm.router import choose
from investia.tools.base import BaseTool, ToolError
from investia.tracing.otel import current_run_id, start_chat_span, start_tool_span
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
    plan: Plan | None = None


DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_CORRECTIONS = 2
# Validation humaine (D57) : pas de réponse = pas d'ordre.
DEFAULT_APPROVAL_TIMEOUT = 300.0


async def run_agent(
    question: str,
    llm: LlmChat,
    tools: dict[str, BaseTool],
    max_turns: int = DEFAULT_MAX_TURNS,
    model_key: str | None = None,
    max_corrections: int = DEFAULT_MAX_CORRECTIONS,
    trace_store: TraceStoreProtocol | None = None,
    event_sink: Any | None = None,
    approval_registry: ApprovalRegistry | None = None,
    approval_timeout: float = DEFAULT_APPROVAL_TIMEOUT,
    reasoning: str = "none",
) -> AgentResult:
    """Boucle d'agent + garde-fous. Arrêt propre si max tours/corrections atteints."""
    from investia.agent.prompts import SYSTEM_PROMPT

    if reasoning not in ("none", "plan"):
        raise ValueError(f"reasoning inconnu : {reasoning!r} (attendu : 'none' ou 'plan')")
    model_key = model_key or choose(question)
    store = trace_store
    run_id = await store.start_run(question) if store is not None else None
    # Les spans OTel de ce run portent ce run_id (ContextVar lu par l'exporter).
    token = current_run_id.set(run_id)

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            await event_sink(kind, payload)

    await emit(
        "start", {"question": question, "max_turns": max_turns, "run_id": run_id}
    )
    plan: Plan | None = None
    total_cost = 0.0
    if reasoning == "plan":
        # Étape 12a : appel LLM dédié, le plan est tracé puis suivi par la métrique plan_suivi.
        plan, plan_cost = await make_plan(
            llm, model_key, question, [tool.name for tool in tools.values()]
        )
        total_cost += plan_cost
        plan_payload = {
            "steps": [{"step": s.step, "tool": s.tool} for s in plan.steps],
            "cost_cents": plan_cost,
        }
        await emit("plan", plan_payload)
        if store is not None and run_id is not None:
            await store.log_step(run_id, 0, "plan", plan_payload)
    tool_specs = [tool.to_openai_tool() for tool in tools.values()]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    log: list[ToolCallLog] = []
    guardrails: list[GuardrailDecision] = []
    corrections = 0

    for turn in range(1, max_turns + 1):
        async with start_chat_span(model=model_key, model_key=model_key) as span_attrs:
            response = await llm.chat(model_key, messages, tools=tool_specs)
            span_attrs["gen_ai.usage.input_tokens"] = response.prompt_tokens
            span_attrs["gen_ai.usage.output_tokens"] = response.completion_tokens
            span_attrs["gen_ai.request.model"] = response.model
            span_attrs["gen_ai.response.model"] = response.model
            span_attrs["cost_cents"] = response.cost_cents
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
                if (
                    call.name == "simulate_order"
                    and approval_registry is not None
                    and run_id is not None
                ):
                    # Validation humaine (D57) : on s'arrête et on attend l'accord.
                    result_text = await _request_approval(
                        tools,
                        call,
                        run_id,
                        turn,
                        approval_registry,
                        approval_timeout,
                        store,
                        emit,
                    )
                else:
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
                plan=plan,
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
            current_run_id.reset(token)
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
            plan=plan,
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
        current_run_id.reset(token)
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
        plan=plan,
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
    current_run_id.reset(token)
    return result


async def _execute_tool(
    tools: dict[str, BaseTool], name: str, arguments: dict[str, Any]
) -> str:
    """Exécute un outil (span OTel tool.call) ; l'erreur va au modèle."""
    tool = tools.get(name)
    if tool is None:
        return f"erreur: outil inconnu {name!r}"
    async with start_tool_span(name, arguments):
        try:
            args = tool.args_schema.model_validate(arguments)
            result = await tool.run(args)
        except ValidationError as error:
            return (
                f"erreur: arguments invalides pour {name} — {error.errors()[0]['msg']}"
            )
        except ToolError as error:
            return f"erreur: {error}"
        return json.dumps(result, default=str, ensure_ascii=False)


async def _request_approval(
    tools: dict[str, BaseTool],
    call: Any,
    run_id: str,
    turn: int,
    registry: ApprovalRegistry,
    timeout: float,
    store: TraceStoreProtocol | None,
    emit: Any,
) -> str:
    """Intercepte simulate_order : émet approval_request, attend la décision humaine.

    « approved » → l'ordre est exécuté. « refused » ou « timeout » → aucun ordre,
    et le modèle reçoit un message clair (pas de réponse = pas d'ordre, D57).
    """
    tool = tools.get("simulate_order")
    if tool is None:
        return f"erreur: outil inconnu {call.name!r}"
    try:
        args = tool.args_schema.model_validate(call.arguments)
    except ValidationError as error:
        msg = error.errors()[0]["msg"]
        return f"erreur: arguments invalides pour simulate_order — {msg}"
    symbol = args.symbol.strip().upper()
    request = {
        "run_id": run_id,
        "turn": turn,
        "symbol": symbol,
        "side": args.side,
        "quantity": args.quantity,
    }
    await emit("approval_request", request)
    if store is not None:
        await store.log_step(
            run_id, turn, "approval_request", {**request, "status": "pending"}
        )
    registry.open(run_id)
    try:
        decision = await registry.wait(run_id, timeout)
    finally:
        registry.close(run_id)
    if store is not None:
        await store.log_step(run_id, turn, "approval", {"decision": decision})
    await emit(
        "approval",
        {
            "turn": turn,
            "decision": decision,
            "symbol": symbol,
            "side": args.side,
            "quantity": args.quantity,
        },
    )
    if decision == "approved":
        return await _execute_tool(tools, call.name, call.arguments)
    if decision == "timeout":
        return (
            "ordre refusé (timeout : pas de réponse = pas d'ordre) — "
            "aucun ordre exécuté"
        )
    return "ordre refusé par l'utilisateur — aucun ordre exécuté"
