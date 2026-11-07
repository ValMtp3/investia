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
from a2a.types import Part, Task, TaskState, TaskStatus

from investia.agent import run_agent
from investia.guardrails import run_all_checks

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


class AnalysteExecutor(AgentExecutor):
    """L'analyste : boucle agent complète (outils + portefeuille) → analyse brute."""

    def __init__(self, llm: Any, tools: dict[str, Any]) -> None:
        self._llm = llm
        self._tools = tools

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = await _begin_task(context, event_queue)
        await updater.start_work()
        question = _user_text(context)
        result = await run_agent(question, self._llm, self._tools)
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

    def __init__(self, llm: Any, tools: dict[str, Any]) -> None:
        self._llm = llm
        self._tools = tools

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = await _begin_task(context, event_queue)
        await updater.start_work()
        data = _parse_json_input(context)
        prompt = (
            "Tu es le rédacteur final d'une chaîne d'agents (simulation). "
            "Analyse de l'analyste :\n"
            f"{data.get('analysis', '')}\n\n"
            f"Verdict du risque : {data.get('verdict', '')}\n\n"
            "Rédige la réponse finale au format imposé (Thèse / Risques / Confiance / "
            "Sources) avec la mention « Simulation — pas un conseil en "
            "investissement. »"
        )
        result = await run_agent(prompt, self._llm, self._tools)
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
