"""Orchestrateur multi-agents (étape 6.1, D60) : enchaîne analyste → risque → rédacteur
en appelant chaque agent par le vrai protocole A2A (JSON-RPC), trace chaque délégation
en base (kind `a2a_delegate`) et émet des événements SSE.

Le `caller` est injectable : en prod un `HttpA2ACaller` (client a2a-sdk vers les agents
montés dans le backend), en test un fake qui appelle la logique directement.
"""

import asyncio
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
    """Appelle un agent A2A par son nom et renvoie son artifact (dict).

    20c : `on_event` (optionnel) reçoit chaque artifact intermédiaire "step"
    de l'agent sous la forme (kind, payload).
    """

    async def call(
        self, agent: str, text: str, on_event: Any | None = None
    ) -> dict[str, Any]: ...


class HttpA2ACaller:
    """Client A2A réel : résout l'agent card puis envoie un message JSON-RPC."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or default_base_url()).rstrip("/")

    async def call(
        self, agent: str, text: str, on_event: Any | None = None
    ) -> dict[str, Any]:
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
            # 20c : forward des steps intermédiaires (artifacts "step")
            if on_event is not None:
                step = _extract_step_event(event)
                if step is not None:
                    try:
                        await on_event(step[0], step[1])
                    except Exception:
                        logger.exception("a2a on_event: erreur avalée")
            artifact_text = _extract_artifact_text(event) or artifact_text
        if not artifact_text:
            raise RuntimeError(f"agent {agent}: aucun artifact reçu")
        try:
            data = json.loads(artifact_text)
            return data if isinstance(data, dict) else {"text": artifact_text}
        except json.JSONDecodeError:
            return {"text": artifact_text}


def _iter_artifacts(event: Any):
    """Itère les artifacts d'un StreamResponse A2A (oneof payload)."""
    for oneof in event.DESCRIPTOR.oneofs:
        which = event.WhichOneof(oneof.name)
        if not which:
            continue
        payload = getattr(event, which)
        for artifact in getattr(payload, "artifacts", None) or []:
            yield artifact
        artifact = getattr(payload, "artifact", None)
        if artifact is not None:
            yield artifact


def _extract_artifact_text(event: Any) -> str | None:
    """Texte de l'artifact final d'un StreamResponse A2A.

    20c : les artifacts intermédiaires nommés "step" sont ignorés (ils sont
    forwardés séparément via _extract_step_event).
    """
    for oneof in event.DESCRIPTOR.oneofs:
        which = event.WhichOneof(oneof.name)
        if not which:
            continue
        payload = getattr(event, which)
        parts: list[Any] = list(getattr(payload, "parts", None) or [])
        for artifact in _iter_artifacts(event):
            if getattr(artifact, "name", "") == "step":
                continue
            parts.extend(getattr(artifact, "parts", None) or [])
        for part in reversed(parts):
            text = getattr(part, "text", None)
            if text:
                return text
    return None


def _extract_step_event(event: Any) -> tuple[str, dict[str, Any]] | None:
    """20c : extrait un artifact "step" d'un StreamResponse A2A.

    Retourne (kind, payload) si l'artifact "step" contient un JSON
    {"kind": ..., "payload": ...}, sinon None (JSON illisible avalé).
    """
    for artifact in _iter_artifacts(event):
        if getattr(artifact, "name", "") != "step":
            continue
        for part in getattr(artifact, "parts", None) or []:
            text = getattr(part, "text", None)
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None
            if isinstance(data, dict) and "kind" in data:
                payload = data.get("payload")
                return str(data["kind"]), payload if isinstance(payload, dict) else {}
            return None
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
    forward_agent_events: bool = False,
    parallel: bool = True,
) -> AgentResult:
    """Enchaîne les agents A2A. Le verdict du risque bloque la réponse si non ok.

    18a : `router` (AgentRouter) choisit quels agents déléguer selon la question
    et leurs succès passés (event `a2a_route`, feedback `record` en fin de run).
    `router=None` = pipeline fixe analyste → risque → rédacteur (6.1, inchangé).
    20c : `forward_agent_events=True` réémet les events internes de chaque
    sous-agent en events SSE `a2a_event` {agent, event_kind, payload}.
    Défaut False = aucun a2a_event (zéro régression).
    24a : `parallel=True` (défaut) exécute les agents par niveaux topologiques
    (`agents/plan.py`) — les agents indépendants d'un même niveau tournent en
    parallèle (asyncio.gather, event `a2a_parallel`), un échec attend la fin
    du niveau puis bloque le run. Le pipeline canonique est une chaîne linéaire
    : comportement strictement identique. `parallel=False` = boucle séquentielle.
    """
    from investia.agents.plan import produced_fields, topological_levels
    from investia.agents.router import CANONICAL_PIPELINE, RISK_AGENT

    caller = caller or HttpA2ACaller()
    run_id = await trace_store.start_run(question) if trace_store is not None else None

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            await event_sink(kind, payload)

    async def delegate(agent: str, text: str, level: int = 0) -> dict[str, Any]:
        # 24a : `level` = niveau topologique de l'agent dans le plan d'exécution
        await emit(
            "a2a_delegate", {"agent": agent, "status": "running", "level": level}
        )
        try:
            if forward_agent_events:
                # 20c : forward des steps internes du sous-agent en SSE
                async def on_event(kind: str, payload: dict[str, Any]) -> None:
                    await emit(
                        "a2a_event",
                        {"agent": agent, "event_kind": kind, "payload": payload},
                    )

                data = await caller.call(agent, text, on_event=on_event)
            else:
                data = await caller.call(agent, text)
            status = "ok"
        except Exception:
            logger.exception("a2a_delegate %s a échoué", agent)
            status = "error"
            data = None
        # Un seul step tracé par délégation : le statut final.
        if trace_store is not None and run_id is not None:
            await trace_store.log_step(
                run_id,
                1,
                "a2a_delegate",
                {"agent": agent, "status": status, "level": level},
            )
        await emit("a2a_delegate", {"agent": agent, "status": status, "level": level})
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
    # 24a : niveaux topologiques ; en séquentiel (parallel=False) chaque agent
    # est son propre niveau, ce qui reproduit exactement l'ancienne boucle.
    levels = topological_levels(agents) if parallel else [[a] for a in agents]
    last_level_idx = len(levels) - 1
    for level_idx, level in enumerate(levels):
        if parallel and len(level) > 1:
            parallel_payload = {"agents": list(level), "level": level_idx}
            await emit("a2a_parallel", parallel_payload)
            if trace_store is not None and run_id is not None:
                await trace_store.log_step(run_id, 0, "a2a_parallel", parallel_payload)
        # Niveau 0 = la question brute ; niveaux suivants = le contexte cumulé.
        if level_idx == 0:
            payload = question
        else:
            payload = json.dumps(context, ensure_ascii=False)
        if parallel and len(level) > 1:
            # On attend tout le niveau avant de décider : un agent en échec
            # bloque le run seulement après que ses voisins aient terminé.
            outcomes = await asyncio.gather(
                *(delegate(agent, payload, level_idx) for agent in level),
                return_exceptions=True,
            )
        else:
            outcomes = [await delegate(agent, payload, level_idx) for agent in level]
        for agent, outcome in zip(level, outcomes):
            if isinstance(outcome, BaseException):
                raise RuntimeError(f"agent {agent} indisponible") from outcome
            data = outcome
            used.append(agent)
            if agent == RISK_AGENT:
                if not data.get("ok", False):
                    failures = "; ".join(
                        f"{name}: {detail}" for name, detail in data.get("failures", [])
                    )
                    answer = (
                        "[réponse bloquée par le gestionnaire de risque : "
                        + failures
                        + "]"
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
                        agents_used=list(used),
                    )
                context["verdict"] = data
            else:
                text = str(
                    data.get("analysis") or data.get("answer") or data.get("text") or ""
                )
                # 24b : chaque agent racine écrit son propre champ du contexte
                # (analyste -> "analysis", macro -> "macro", news -> "news"),
                # lu depuis la clé correspondante de son artifact.
                for field_name in produced_fields(agent):
                    context[field_name] = str(data.get(field_name) or text)
                if level_idx == last_level_idx and agent == level[-1]:
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
    return AgentResult(
        answer=answer,
        turns=len(used),
        model="multi-agent",
        status="ok",
        agents_used=list(used),
    )
