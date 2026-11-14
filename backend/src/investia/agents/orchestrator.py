"""Orchestrateur multi-agents (étape 6.1, D60) : enchaîne analyste → risque → rédacteur
en appelant chaque agent par le vrai protocole A2A (JSON-RPC), trace chaque délégation
en base (kind `a2a_delegate`) et émet des événements SSE.

Le `caller` est injectable : en prod un `HttpA2ACaller` (client a2a-sdk vers les agents
montés dans le backend), en test un fake qui appelle la logique directement.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from investia.agent.loop import AgentResult

logger = logging.getLogger(__name__)

# Alias Docker unique du backend (D53) : en prod, les agents se parlent en HTTP interne.
DEFAULT_A2A_BASE_URL = "http://investia-backend:8000"


def default_base_url() -> str:
    """Base A2A : alias Docker en prod, surchargeable en local (A2A_BASE_URL)."""
    return os.environ.get("A2A_BASE_URL", DEFAULT_A2A_BASE_URL)


class AgentCaller(Protocol):
    """Appelle un agent A2A par son nom et renvoie son artifact (dict)."""

    async def call(self, agent: str, text: str) -> dict[str, Any]: ...


class HttpA2ACaller:
    """Client A2A réel : résout l'agent card puis envoie un message JSON-RPC."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or default_base_url()).rstrip("/")

    async def call(self, agent: str, text: str) -> dict[str, Any]:
        from a2a.client import create_client
        from a2a.types import Message, Part, SendMessageRequest

        client = await create_client(f"{self._base_url}/api/agents/{agent}")
        message = Message(
            role="ROLE_USER",
            parts=[Part(text=text)],
            message_id=uuid4().hex,
        )
        request = SendMessageRequest(message=message)
        artifact_text = ""
        async for event in client.send_message(request):
            artifact_text = _extract_artifact_text(event) or artifact_text
        if not artifact_text:
            raise RuntimeError(f"agent {agent}: aucun artifact reçu")
        try:
            data = json.loads(artifact_text)
            return data if isinstance(data, dict) else {"text": artifact_text}
        except json.JSONDecodeError:
            return {"text": artifact_text}


def _extract_artifact_text(event: Any) -> str | None:
    """Texte d'artifact d'un StreamResponse A2A (oneof task/message/status/artifact)."""
    for oneof in event.DESCRIPTOR.oneofs:
        which = event.WhichOneof(oneof.name)
        if not which:
            continue
        payload = getattr(event, which)
        parts: list[Any] = list(getattr(payload, "parts", None) or [])
        for artifact in getattr(payload, "artifacts", None) or []:
            parts.extend(getattr(artifact, "parts", None) or [])
        artifact = getattr(payload, "artifact", None)
        if artifact is not None:
            parts.extend(getattr(artifact, "parts", None) or [])
        for part in reversed(parts):
            text = getattr(part, "text", None)
            if text:
                return text
    return None


@dataclass
class MultiAgentResult:
    answer: str
    agents: list[str] = field(default_factory=list)
    status: str = "ok"


async def run_multi_agent(
    question: str,
    llm: Any,
    tools: dict[str, Any],
    trace_store: Any | None = None,
    event_sink: Any | None = None,
    caller: AgentCaller | None = None,
    router: Any | None = None,
) -> AgentResult:
    """Enchaîne les agents A2A. Le verdict du risque bloque la réponse si non ok.

    18a : `router` (AgentRouter) choisit quels agents déléguer selon la question
    et leurs succès passés (event `a2a_route`, feedback `record` en fin de run).
    `router=None` = pipeline fixe analyste → risque → rédacteur (6.1, inchangé).
    """
    from investia.agents.router import CANONICAL_PIPELINE, RISK_AGENT

    caller = caller or HttpA2ACaller()
    run_id = await trace_store.start_run(question) if trace_store is not None else None

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            await event_sink(kind, payload)

    async def delegate(agent: str, text: str) -> dict[str, Any]:
        await emit("a2a_delegate", {"agent": agent, "status": "running"})
        try:
            data = await caller.call(agent, text)
            status = "ok"
        except Exception:
            logger.exception("a2a_delegate %s a échoué", agent)
            status = "error"
            data = None
        # Un seul step tracé par délégation : le statut final.
        if trace_store is not None and run_id is not None:
            await trace_store.log_step(
                run_id, 1, "a2a_delegate", {"agent": agent, "status": status}
            )
        await emit("a2a_delegate", {"agent": agent, "status": status})
        if status == "error" or data is None:
            raise RuntimeError(f"agent {agent} indisponible")
        return data

    await emit("start", {"question": question, "mode": "multi-agent", "run_id": run_id})

    # 18a : délégation dynamique — router appris, sinon pipeline fixe (6.1)
    if router is not None:
        agents, route_source = await router.choose(question)
    else:
        agents, route_source = list(CANONICAL_PIPELINE), "fixed"
    if router is not None:
        # 18a : on ne touche au flux SSE que quand le routage dynamique est actif
        route_payload = {"agents": list(agents), "source": route_source}
        await emit("a2a_route", route_payload)
        if trace_store is not None and run_id is not None:
            await trace_store.log_step(run_id, 0, "a2a_route", route_payload)

    used: list[str] = []

    async def record_feedback(success: bool) -> None:
        """Feedback du routeur d'agents (18a) ; une erreur ne bloque jamais."""
        if router is None:
            return
        try:
            await router.record(question, used, success)
        except Exception:
            logger.exception("agent router feedback: erreur avalée")

    context: dict[str, Any] = {"question": question}
    answer = ""
    for i, agent in enumerate(agents):
        payload = question if i == 0 else json.dumps(context, ensure_ascii=False)
        data = await delegate(agent, payload)
        used.append(agent)
        if agent == RISK_AGENT:
            if not data.get("ok", False):
                failures = "; ".join(
                    f"{name}: {detail}" for name, detail in data.get("failures", [])
                )
                answer = (
                    "[réponse bloquée par le gestionnaire de risque : " + failures + "]"
                )
                await emit("answer", {"text": answer})
                await emit("done", {"status": "blocked", "agents": list(used)})
                if trace_store is not None and run_id is not None:
                    await trace_store.finish_run(
                        run_id,
                        answer=answer,
                        model="multi-agent",
                        turns=len(used),
                        cost_cents=0.0,
                        status="blocked",
                    )
                await record_feedback(False)
                return AgentResult(
                    answer=answer,
                    turns=len(used),
                    model="multi-agent",
                    status="blocked",
                )
            context["verdict"] = data
        else:
            text = str(
                data.get("analysis") or data.get("answer") or data.get("text") or ""
            )
            context["analysis"] = text
            if i == len(agents) - 1:
                answer = text

    await emit("answer", {"text": answer})
    await emit("done", {"status": "ok", "agents": list(used)})
    if trace_store is not None and run_id is not None:
        await trace_store.finish_run(
            run_id,
            answer=answer,
            model="multi-agent",
            turns=len(used),
            cost_cents=0.0,
            status="ok",
        )
    await record_feedback(True)
    return AgentResult(answer=answer, turns=len(used), model="multi-agent", status="ok")
