"""Exécuteurs A2A des 3 agents (étape 6.1).

Chaque exécuteur réutilise les briques existantes du harness (boucle, outils,
garde-fous) : pas de réécriture. L'entrée est le texte du message utilisateur
(`context.get_user_input()`), la sortie un artifact JSON nommé.
"""

import json
import logging
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import Artifact, Part, Task, TaskState, TaskStatus

from investia.agent import run_agent
from investia.guardrails import run_all_checks
from investia.guardrails.injection import wrap_untrusted

logger = logging.getLogger(__name__)


def _user_text(context: RequestContext) -> str:
    return context.get_user_input() or ""


async def _begin_task(context: RequestContext, event_queue: EventQueue) -> TaskUpdater:
    """Crée la Task (état submitted) puis renvoie un TaskUpdater.

    Le protocole A2A exige que la Task soit enfilée avant tout
    TaskStatusUpdateEvent.
    """
    task_id = context.task_id or ""
    context_id = context.context_id or ""
    await event_queue.enqueue_event(
        Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            history=[context.message] if context.message else None,
        )
    )
    return TaskUpdater(event_queue=event_queue, task_id=task_id, context_id=context_id)


def _parse_json_input(context: RequestContext) -> dict[str, Any]:
    """Entrée JSON ({"analysis": ...}) ou texte brut : on tolère les deux."""
    text = _user_text(context)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {"text": text}


# 20c : kinds d'events du harness non forwardés en artifacts "step" (l'orchestrateur
# émet déjà ses propres start/answer/done au niveau du run multi-agent).
_NON_FORWARDED_KINDS = frozenset({"start", "answer", "done", "error"})


def _step_artifact(kind: str, payload: Any) -> Artifact:
    """20c : artifact A2A "step" (JSON kind/payload d'un event du harness)."""
    return Artifact(
        artifact_id=None,
        name="step",
        parts=[
            Part(
                text=json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False)
            )
        ],
    )


def _streaming_sink(updater: TaskUpdater):
    """20c : event_sink pour run_agent — émet les events en artifacts "step"."""

    async def sink(kind: str, payload: Any) -> None:
        if kind in _NON_FORWARDED_KINDS:
            return
        artifact = _step_artifact(kind, payload)
        await updater.add_artifact(
            parts=list(artifact.parts), name="step", last_chunk=False
        )

    return sink


class AnalysteExecutor(AgentExecutor):
    """L'analyste : boucle agent complète (outils + portefeuille) → analyse brute."""

    def __init__(
        self,
        llm: Any,
        tools: dict[str, Any],
        *,
        tool_policy: Any | None = None,
        approval_registry: Any | None = None,
        trace_store: Any | None = None,
        memory_store: Any | None = None,
        semantic_cache: Any | None = None,
        router: Any | None = None,
        context_max_tokens: int | None = None,
        keep_last_turns: int = 4,
    ) -> None:
        self._llm = llm
        self._tools = tools
        # 24 (scan sécurité) : mêmes garde-fous que /agent/run (CWE-306/862/693)
        self._tool_policy = tool_policy
        self._approval_registry = approval_registry
        self._trace_store = trace_store
        self._memory_store = memory_store
        self._semantic_cache = semantic_cache
        self._router = router
        self._context_max_tokens = context_max_tokens
        self._keep_last_turns = keep_last_turns

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = await _begin_task(context, event_queue)
        await updater.start_work()
        question = _user_text(context)
        # 20c : stream des events internes (llm_call, tool_call…) en "step"
        result = await run_agent(
            question,
            self._llm,
            self._tools,
            event_sink=_streaming_sink(updater),
            tool_policy=self._tool_policy,
            approval_registry=self._approval_registry,
            trace_store=self._trace_store,
            memory_store=self._memory_store,
            semantic_cache=self._semantic_cache,
            router=self._router,
            context_max_tokens=self._context_max_tokens,
            keep_last_turns=self._keep_last_turns,
        )
        payload = {
            "analysis": result.answer,
            "turns": result.turns,
            "cost_cents": result.total_cost_cents,
        }
        await updater.add_artifact(
            parts=[Part(text=json.dumps(payload, ensure_ascii=False))],
            name="analysis",
            last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id or "",
            context_id=context.context_id or "",
        )
        await updater.cancel()


class RisqueExecutor(AgentExecutor):
    """Le gestionnaire de risque : garde-fous en code sur l'analyse de l'analyste."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = await _begin_task(context, event_queue)
        await updater.start_work()
        data = _parse_json_input(context)
        analysis = str(data.get("analysis") or data.get("text") or "")
        # Les chiffres de l'analyse viennent des outils de l'analyste : on les
        # repasse comme sorties d'outils connues pour le garde-fou « sourcé ».
        checks = run_all_checks(analysis, tool_outputs=[])
        failures = [[name, result.detail] for name, result in checks if not result.ok]
        payload = {"ok": not failures, "failures": failures}
        await updater.add_artifact(
            parts=[Part(text=json.dumps(payload, ensure_ascii=False))],
            name="verdict",
            last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id or "",
            context_id=context.context_id or "",
        )
        await updater.cancel()


class RedacteurExecutor(AgentExecutor):
    """Le rédacteur : réponse finale structurée à partir de l'analyse + du verdict."""

    def __init__(
        self,
        llm: Any,
        tools: dict[str, Any],
        *,
        tool_policy: Any | None = None,
        trace_store: Any | None = None,
        memory_store: Any | None = None,
        semantic_cache: Any | None = None,
        router: Any | None = None,
        context_max_tokens: int | None = None,
        keep_last_turns: int = 4,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._tool_policy = tool_policy
        self._trace_store = trace_store
        self._memory_store = memory_store
        self._semantic_cache = semantic_cache
        self._router = router
        self._context_max_tokens = context_max_tokens
        self._keep_last_turns = keep_last_turns

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = await _begin_task(context, event_queue)
        await updater.start_work()
        data = _parse_json_input(context)
        # 24 (scan sécurité, CWE-1427) : l'analyse et le verdict viennent d'un
        # autre agent (contenu potentiellement injecté via les outils externes) —
        # délimités comme non fiables avant d'entrer dans le prompt.
        analysis = wrap_untrusted(str(data.get("analysis") or ""))
        verdict = wrap_untrusted(str(data.get("verdict") or ""))
        prompt = (
            "Tu es le rédacteur final d'une chaîne d'agents (simulation). "
            "Analyse de l'analyste :\n"
            f"{analysis}\n\n"
            f"Verdict du risque : {verdict}\n\n"
            "Rédige la réponse finale au format imposé (Thèse / Risques / Confiance / "
            "Sources) avec la mention « Simulation — pas un conseil en "
            "investissement. »"
        )
        # 20c : stream des events internes en artifacts "step"
        result = await run_agent(
            prompt,
            self._llm,
            self._tools,
            event_sink=_streaming_sink(updater),
            tool_policy=self._tool_policy,
            trace_store=self._trace_store,
            memory_store=self._memory_store,
            semantic_cache=self._semantic_cache,
            router=self._router,
            context_max_tokens=self._context_max_tokens,
            keep_last_turns=self._keep_last_turns,
        )
        payload = {"answer": result.answer}
        await updater.add_artifact(
            parts=[Part(text=json.dumps(payload, ensure_ascii=False))],
            name="answer",
            last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id or "",
            context_id=context.context_id or "",
        )
        await updater.cancel()
