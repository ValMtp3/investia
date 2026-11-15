"""La boucle d'agent : réfléchir -> appeler un outil -> lire le résultat -> recommencer.

Écrite à la main (D41), zéro framework. Max N tours + budget par run : dépassement
-> arrêt propre, jamais de boucle infinie.
"""

import asyncio
import inspect
import json
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from pydantic import ValidationError

from investia.agent.approval import ApprovalRegistry, payload_hash_for
from investia.agent.reasoning import (
    Plan,
    ReflectionDecision,
    make_plan,
    reflect,
    vote,
)
from investia.guardrails import run_all_checks
from investia.guardrails.canary import (
    CANARY_BLOCKED_MESSAGE,
    CanaryDetector,
    generate_canary,
)
from investia.guardrails.injection import (
    BLOCKED_MESSAGE,
    InjectionScanner,
    default_injection_scanner,
    wrap_untrusted,
)
from investia.guardrails.llm_check import check_safety_llm, check_safety_logprobs
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
        logprobs: bool = False,
    ) -> LlmResponse: ...


class _CachedTokensTracker:
    """17f : wrapper LLM qui somme les tokens cachés (cache prompt) d'un run.

    Règle « préserver le cache » (opencode v2.2.7) : le modèle est résolu une
    seule fois par run_agent, donc tous les appels ci-dessous réutilisent le
    même préfixe caché côté provider — on les compte pour l'exposer.
    """

    def __init__(self, llm: LlmChat) -> None:
        self._llm = llm
        self.cached_tokens = 0

    async def chat(
        self,
        model_key: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
        logprobs: bool = False,
    ) -> LlmResponse:
        response = await self._llm.chat(
            model_key, messages, temperature=temperature, tools=tools, logprobs=logprobs
        )
        self.cached_tokens += response.cached_tokens
        return response


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
    reflections: list[ReflectionDecision] = field(default_factory=list)
    run_id: str | None = None
    status: str = "ok"  # ok / blocked / max_turns
    from_cache: bool = (
        False  # étape 12e : servi par le cache sémantique, zéro appel LLM
    )
    consensus: float = (
        1.0  # étape 12c : part des k runs d'accord avec la réponse retenue
    )
    answers: list[str] = field(
        default_factory=list
    )  # étape 12c : les k réponses candidates
    router_source: str = "rules"  # étape 12h : explicit | learned | rules
    model_key: str = ""  # étape 12h : clé résolue (small/large) choisie pour ce run
    agents_used: list[str] = field(
        default_factory=list
    )  # étape 18b : agents A2A délégués (multi-agent uniquement)
    injections_blocked: int = 0  # étape 13b : sorties d'outils externes bloquées
    canary_hits: int = 0  # étape 23b : canary du run retrouvé hors contenu externe
    compactions: int = 0  # étape 16c : compactions du contexte effectuées
    cached_tokens: int = 0  # 17f : tokens input servis depuis le cache prompt


DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_CORRECTIONS = 2
# Étape 12 : modes de raisonnement structurés, combinables par « + » ("plan+reflect").
REASONING_MODES = frozenset({"plan", "reflect"})


def _parse_reasoning_modes(reasoning: str) -> set[str]:
    if reasoning == "none":
        return {"none"}
    modes = set(reasoning.split("+"))
    if not modes <= REASONING_MODES:
        raise ValueError(
            f"reasoning inconnu : {reasoning!r} "
            "(attendu : 'none', 'plan', 'reflect' ou 'plan+reflect')"
        )
    return modes


# Validation humaine (D57) : pas de réponse = pas d'ordre.
DEFAULT_APPROVAL_TIMEOUT = 300.0


async def _run_once(
    question: str,
    llm: LlmChat,
    tools: dict[str, BaseTool],
    modes: set[str],
    model_key: str,
    max_turns: int = DEFAULT_MAX_TURNS,
    max_corrections: int = DEFAULT_MAX_CORRECTIONS,
    trace_store: TraceStoreProtocol | None = None,
    event_sink: Any | None = None,
    approval_registry: ApprovalRegistry | None = None,
    approval_timeout: float = DEFAULT_APPROVAL_TIMEOUT,
    decision_client: Any | None = None,
    logprobs_guardrail: bool = False,
    router_source: str = "rules",
    injection_scanner: InjectionScanner | None = None,
    injection_policy: str = "block",
    canary_token: str | None = None,
    context_max_tokens: int | None = None,
    keep_last_turns: int = 4,
    memory_store: Any | None = None,
    pre_compact: Any | None = None,
    tool_policy: Any | None = None,
) -> AgentResult:
    """Un run de la boucle + garde-fous (corps historique, extrait en étape 12c).

    16c : context_max_tokens déclenche une compaction du contexte par tour
    (sliding window, résumé « untrusted », memory flush via memory_store).
    None = désactivé (comportement historique).

    17d : pre_compact — hook bloquant appelé avant chaque compaction,
    `(messages, estimated_tokens, context_max_tokens) -> bool` (sync ou async).
    False = veto : pas de compaction ce tour, event « compaction_vetoed ».
    None = autoriser (comportement 16c).

    17e : tool_policy — set de noms autorisés OU callable `(name) -> bool`
    (sync ou async). Appliquée AVANT les tool_specs : un outil refusé n'est
    jamais envoyé au modèle (pas de schéma). None = tous les outils.
    """
    from investia.agent.prompts import SYSTEM_PROMPT

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
    # 17e : tool policy pré-schéma — un outil refusé n'est pas envoyé au modèle.
    all_tool_names = set(tools)
    if tool_policy is not None:

        async def _allows(name: str) -> bool:
            if callable(tool_policy):
                ok = tool_policy(name)
                if inspect.isawaitable(ok):
                    ok = await ok
                return bool(ok)
            return name in tool_policy  # set / frozenset de noms autorisés

        tools = {n: t for n, t in tools.items() if await _allows(n)}
    policy_payload = {
        "kept": sorted(tools),
        "withheld": sorted(all_tool_names - set(tools)),
    }
    await emit("tool_policy", policy_payload)
    if store is not None and run_id is not None:
        await store.log_step(run_id, 0, "tool_policy", policy_payload)
    # 17f : on somme les tokens cachés de tous les appels LLM du run
    llm = _CachedTokensTracker(llm)
    plan: Plan | None = None
    reflections: list[ReflectionDecision] = []
    total_cost = 0.0
    if "plan" in modes:
        # Étape 12a : appel LLM dédié, plan tracé + métrique plan_suivi.
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
    # Étape 13b : scan anti-injection des sorties d'outils externes.
    if injection_policy not in {"block", "warn"}:
        raise ValueError(
            f"injection_policy inconnu : {injection_policy!r} "
            "(attendu : 'block' ou 'warn')"
        )
    if injection_scanner is not None:
        scanner = injection_scanner
    else:
        scanner = default_injection_scanner()
    injections_blocked = 0
    # 23b : canary token du run — injecté dans le contenu externe wrappé, puis
    # recherché dans les tool_calls suivants et la réponse finale (exfiltration).
    canary_detector = CanaryDetector(canary_token or generate_canary())
    canary_hits = 0
    compactions = 0

    for turn in range(1, max_turns + 1):
        # 16c : compaction du contexte si le seuil est dépassé (avant l'appel LLM).
        if context_max_tokens is not None:
            from investia.agent.compaction import (
                compact_messages,
                estimate_tokens,
                parse_memoires,
            )

            estimated = estimate_tokens(messages)
            if estimated > context_max_tokens:
                # 17d : hook PreCompact bloquant (sync ou async) — False = veto.
                allow = True
                if pre_compact is not None:
                    outcome = pre_compact(messages, estimated, context_max_tokens)
                    if inspect.isawaitable(outcome):
                        outcome = await outcome
                    allow = bool(outcome)
                compaction_meta: dict[str, Any] = {"compacted": False}
                if not allow:
                    veto_payload = {
                        "turn": turn,
                        "estimated_tokens": estimated,
                        "context_max_tokens": context_max_tokens,
                    }
                    await emit("compaction_vetoed", veto_payload)
                    if store is not None and run_id is not None:
                        await store.log_step(
                            run_id, turn, "compaction_vetoed", veto_payload
                        )
                else:
                    messages, compaction_meta = await compact_messages(
                        messages,
                        llm=llm,
                        model_key=model_key,
                        max_tokens=context_max_tokens,
                        keep_last_turns=keep_last_turns,
                    )
                if compaction_meta["compacted"]:
                    compactions += 1
                    total_cost += compaction_meta["cost_cents"]
                    memoires = parse_memoires(compaction_meta["summary"])
                    if memory_store is not None:
                        for fait in memoires:
                            try:
                                await memory_store.save(fait, None)
                            except Exception:
                                pass  # le flush mémoire ne bloque jamais le run
                    compaction_payload = {
                        "turn": turn,
                        "dropped_messages": compaction_meta["dropped_messages"],
                        "summary_chars": len(compaction_meta["summary"]),
                        "memoires": memoires,
                        "cost_cents": compaction_meta["cost_cents"],
                    }
                    await emit("compaction", compaction_payload)
                    if store is not None and run_id is not None:
                        await store.log_step(
                            run_id, turn, "compaction", compaction_payload
                        )
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
                # 23b : le canary du run dans les arguments = exfiltration de
                # contenu externe → on compte, on trace, et en policy "block"
                # le tool_call n'est pas exécuté.
                leaked = canary_detector.scan(json.dumps(call.arguments))
                if leaked:
                    canary_hits += 1
                    await emit(
                        "canary_hit",
                        {"turn": turn, "tool": call.name, "where": "arguments"},
                    )
                    if store is not None and run_id is not None:
                        await store.log_step(
                            run_id,
                            turn,
                            "canary_hit",
                            {"tool": call.name, "where": "arguments"},
                        )
                if leaked and injection_policy == "block":
                    result_text = CANARY_BLOCKED_MESSAGE
                elif (
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
                # 13b : sortie d'outil externe → scan injection + délimitation.
                tool = tools.get(call.name)
                if tool is not None and getattr(tool, "untrusted_output", False):
                    scan = scanner.scan(result_text)
                    if scan.verdict == "blocked" and injection_policy == "block":
                        injections_blocked += 1
                        await emit(
                            "injection",
                            {
                                "turn": turn,
                                "tool": call.name,
                                "verdict": scan.verdict,
                                "detail": scan.detail,
                            },
                        )
                        if store is not None and run_id is not None:
                            await store.log_step(
                                run_id,
                                turn,
                                "injection",
                                {
                                    "tool": call.name,
                                    "verdict": scan.verdict,
                                    "detail": scan.detail,
                                },
                            )
                        result_text = BLOCKED_MESSAGE
                    else:
                        # 23b : le canary du run est injecté dans le délimiteur.
                        result_text = wrap_untrusted(
                            result_text, canary=canary_detector.token
                        )
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

        # Réponse finale : auto-critique (12b) puis garde-fous en code avant validation.
        tool_outputs = [m["content"] for m in messages if m.get("role") == "tool"]
        reflection_failed: tuple[str, str] | None = None
        if "reflect" in modes:
            decision, reflect_cost = await reflect(
                llm, model_key, response.content, tool_outputs
            )
            total_cost += reflect_cost
            reflections.append(decision)
            await emit(
                "reflection",
                {
                    "turn": turn,
                    "ok": decision.ok,
                    "problemes": decision.problemes,
                    "cost_cents": reflect_cost,
                },
            )
            if store is not None and run_id is not None:
                await store.log_step(
                    run_id,
                    turn,
                    "reflection",
                    {
                        "ok": decision.ok,
                        "problemes": decision.problemes,
                        "cost_cents": reflect_cost,
                    },
                )
            if not decision.ok:
                reflection_failed = (
                    "reflection",
                    "; ".join(decision.problemes)
                    or "problèmes signalés par l'auto-critique",
                )
        checks = run_all_checks(response.content, tool_outputs)
        # Étape 12d : garde-fous LLM en renfort (jamais à la place du code).
        if decision_client is not None:
            checks.append(
                (
                    "safety_llm",
                    await check_safety_llm(response.content, decision_client.decide),
                )
            )
        if logprobs_guardrail:
            checks.append(
                (
                    "safety_logprobs",
                    await check_safety_logprobs(response.content, llm, model_key),
                )
            )
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
        if reflection_failed is not None:
            failed.append(reflection_failed)
        if not failed:
            # 23b : canary dans la réponse finale → on trace et on rédige.
            final_text = response.content
            if canary_detector.scan(final_text):
                canary_hits += 1
                await emit("canary_hit", {"turn": turn, "where": "answer"})
                if store is not None and run_id is not None:
                    await store.log_step(
                        run_id, turn, "canary_hit", {"where": "answer"}
                    )
                final_text = canary_detector.redact(final_text)
            await emit("answer", {"turn": turn, "text": final_text})
            result = AgentResult(
                answer=final_text,
                turns=turn,
                tool_calls=log,
                total_cost_cents=total_cost,
                model=response.model,
                guardrails=guardrails,
                plan=plan,
                reflections=reflections,
                run_id=run_id,
                status="ok",
                router_source=router_source,
                model_key=model_key,
                injections_blocked=injections_blocked,
                canary_hits=canary_hits,
                compactions=compactions,
                cached_tokens=llm.cached_tokens,
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
                    # 17f : coût/run exposé — modèle choisi, source du routage,
                    # tokens servis depuis le cache prompt
                    "model": model_key,
                    "router_source": router_source,
                    "cached_tokens": llm.cached_tokens,
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
            reflections=reflections,
            run_id=run_id,
            status="blocked",
            router_source=router_source,
            model_key=model_key,
            compactions=compactions,
            cached_tokens=llm.cached_tokens,
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
                "model": model_key,
                "router_source": router_source,
                "cached_tokens": llm.cached_tokens,
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
        reflections=reflections,
        run_id=run_id,
        status="max_turns",
        router_source=router_source,
        model_key=model_key,
        injections_blocked=injections_blocked,
        compactions=compactions,
        cached_tokens=llm.cached_tokens,
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
            "model": model_key,
            "router_source": router_source,
            "cached_tokens": llm.cached_tokens,
        },
    )
    current_run_id.reset(token)
    return result


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
    consistency_k: int = 1,
    llm_factory: Any | None = None,
    decision_client: Any | None = None,
    logprobs_guardrail: bool = False,
    semantic_cache: Any | None = None,
    router: Any | None = None,
    injection_scanner: InjectionScanner | None = None,
    injection_policy: str = "block",
    canary_token: str | None = None,
    context_max_tokens: int | None = None,
    keep_last_turns: int = 4,
    memory_store: Any | None = None,
    pre_compact: Any | None = None,
    tool_policy: Any | None = None,
) -> AgentResult:
    """Boucle d'agent + reasoning structuré (12a/12b) + self-consistency (12c).

    16c : context_max_tokens (None = off) déclenche la compaction du contexte.

    consistency_k > 1 : k sous-runs en parallèle (chacun tracé en base), vote
    majoritaire sur la réponse finale, event/step « consensus » dans le run
    gagnant. Non combinable avec la validation humaine (approval_registry).

    router (étape 12h) : routeur appris petit/gros modèle ; model_key explicite
    reste prioritaire. Après chaque run (hors cache), un feedback est enregistré.
    """
    modes = _parse_reasoning_modes(reasoning)
    if consistency_k < 1:
        raise ValueError(f"consistency_k invalide : {consistency_k} (attendu >= 1)")
    if consistency_k > 1 and approval_registry is not None:
        raise ValueError(
            "consistency_k > 1 non combinable avec approval_registry "
            "(validation humaine)"
        )
    if injection_policy not in {"block", "warn"}:
        raise ValueError(
            f"injection_policy inconnu : {injection_policy!r} "
            "(attendu : 'block' ou 'warn')"
        )
    if model_key is not None:
        resolved_model = model_key
        router_source = "explicit"
    elif router is not None:
        resolved_model, router_source = await router.choose(question)
    else:
        resolved_model = choose(question)
        router_source = "rules"

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            await event_sink(kind, payload)

    async def store_cache(answer: str) -> None:
        """Stocke la réponse dans le cache sémantique si ok ; erreur avalée."""
        if semantic_cache is None:
            return
        try:
            await semantic_cache.store(question, answer)
        except Exception:
            pass

    async def record_feedback(status: str) -> None:
        """Feedback du routeur appris (12h) ; une erreur ne bloque jamais le run."""
        if router is None:
            return
        try:
            await router.record(question, resolved_model, status == "ok")
        except Exception:
            pass

    # Étape 12e : cache sémantique — question déjà répondue = servie sans appel LLM.
    if semantic_cache is not None:
        try:
            hit = await semantic_cache.lookup(question)
        except Exception:
            hit = None
        if hit is not None:
            await emit("start", {"question": question, "from_cache": True})
            await emit("cache_hit", {"question": question})
            await emit("answer", {"turn": 0, "text": hit})
            await emit(
                "done",
                {
                    "turns": 0,
                    "cost_cents": 0.0,
                    "status": "ok",
                    "model": "cache",
                    "router_source": router_source,
                    "cached_tokens": 0,
                },
            )
            return AgentResult(
                answer=hit,
                turns=0,
                total_cost_cents=0.0,
                model="cache",
                status="ok",
                from_cache=True,
                router_source=router_source,
                model_key=resolved_model,
            )

    if consistency_k == 1:
        result = await _run_once(
            question,
            llm,
            tools,
            modes,
            resolved_model,
            max_turns=max_turns,
            max_corrections=max_corrections,
            trace_store=trace_store,
            event_sink=event_sink,
            approval_registry=approval_registry,
            approval_timeout=approval_timeout,
            decision_client=decision_client,
            logprobs_guardrail=logprobs_guardrail,
            router_source=router_source,
            injection_scanner=injection_scanner,
            injection_policy=injection_policy,
            canary_token=canary_token,
            context_max_tokens=context_max_tokens,
            keep_last_turns=keep_last_turns,
            memory_store=memory_store,
            pre_compact=pre_compact,
            tool_policy=tool_policy,
        )
        if result.status == "ok":
            await store_cache(result.answer)
        await record_feedback(result.status)
        return result

    await emit("start", {"question": question, "consistency_k": consistency_k})

    async def one(i: int) -> AgentResult:
        client = llm_factory(i) if llm_factory is not None else llm
        return await _run_once(
            question,
            client,
            tools,
            modes,
            resolved_model,
            max_turns=max_turns,
            max_corrections=max_corrections,
            trace_store=trace_store,
            event_sink=None,  # pas de SSE entremêlée : chaque sous-run trace en base
            approval_registry=None,
            approval_timeout=approval_timeout,
            decision_client=decision_client,
            logprobs_guardrail=logprobs_guardrail,
            router_source=router_source,
            injection_scanner=injection_scanner,
            injection_policy=injection_policy,
            canary_token=canary_token,
            context_max_tokens=context_max_tokens,
            keep_last_turns=keep_last_turns,
            memory_store=memory_store,
            pre_compact=pre_compact,
            tool_policy=tool_policy,
        )

    results = list(await asyncio.gather(*(one(i) for i in range(consistency_k))))
    winner_index, consensus = vote([r.answer for r in results])
    winner = results[winner_index]
    answers = [r.answer for r in results]
    consensus_payload = {
        "k": consistency_k,
        "winner": winner_index,
        "consensus": consensus,
        "answers": answers,
    }
    await emit("consensus", consensus_payload)
    if trace_store is not None and winner.run_id is not None:
        await trace_store.log_step(winner.run_id, 0, "consensus", consensus_payload)
    total_cost = sum(r.total_cost_cents for r in results)
    result = replace(
        winner, consensus=consensus, answers=answers, total_cost_cents=total_cost
    )
    if result.status == "ok":
        await store_cache(result.answer)
    await record_feedback(result.status)
    await emit("answer", {"turn": result.turns, "text": result.answer})
    await emit(
        "done",
        {"turns": result.turns, "cost_cents": result.total_cost_cents, "status": "ok"},
    )
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
    # 13d : l'approbation est liée au hash exact du payload affiché.
    payload_hash = payload_hash_for(symbol, args.side, args.quantity)
    request = {
        "run_id": run_id,
        "turn": turn,
        "symbol": symbol,
        "side": args.side,
        "quantity": args.quantity,
        "payload_hash": payload_hash,
    }
    await emit("approval_request", request)
    if store is not None:
        await store.log_step(
            run_id, turn, "approval_request", {**request, "status": "pending"}
        )
    registry.open(run_id, payload_hash=payload_hash)
    try:
        decision = await registry.wait(run_id, timeout)
    finally:
        registry.close(run_id)
    if store is not None:
        await store.log_step(
            run_id,
            turn,
            "approval",
            {"decision": decision, "payload_hash": payload_hash},
        )
    await emit(
        "approval",
        {
            "turn": turn,
            "decision": decision,
            "symbol": symbol,
            "side": args.side,
            "quantity": args.quantity,
            "payload_hash": payload_hash,
        },
    )
    if decision == "approved":
        # 13d : re-vérification du hash avant exécution (anti replan-after-yes).
        approved = getattr(registry, "approved_hash", lambda _rid: None)(run_id)
        if approved is not None and approved != payload_hash:
            return (
                "ordre refusé (payload modifié après approbation) — aucun ordre exécuté"
            )
        return await _execute_tool(tools, call.name, call.arguments)
    if decision == "timeout":
        return (
            "ordre refusé (timeout : pas de réponse = pas d'ordre) — "
            "aucun ordre exécuté"
        )
    return "ordre refusé par l'utilisateur — aucun ordre exécuté"
