"""Mapping des événements maison (kind, payload) vers le protocole AG-UI.

AG-UI transporte chaque événement dans un bloc SSE `data: {json}\n\n` dont le
champ `type` porte le nom de l'événement (ex. RUN_STARTED) — il n'y a PAS de
ligne `event:`. La boucle `run_agent` n'est pas modifiée : ce mapping vit côté
sink, dans la route POST /agent/run (paramètre `protocol=agui`).

Les kinds natifs AG-UI (start/answer/tool_call/done/error) ont leur événement
dédié ; tout le reste (llm_call, guardrail, approval_request, ...) passe en
CustomEvent nommé, pour ne rien perdre côté client.
"""

import json
from typing import Any
from uuid import uuid4

from ag_ui.core import events as agui_events
from ag_ui.core.events import BaseEvent
from ag_ui.core.types import RunAgentInput

# Kinds transportés tels quels en CustomEvent(name=kind, value=payload).
CUSTOM_KINDS = frozenset(
    {
        "llm_call",
        "guardrail",
        "injection",
        "approval_request",
        "approval",
        "plan",
        "reflection",
        "consensus",
        "cache_hit",
        "compaction",
    }
)


def _text_message_id(payload: dict[str, Any]) -> str:
    """message_id stable pour le triplet start/content/end d'une réponse."""
    return str(payload.get("message_id") or f"msg-{uuid4().hex}")


def to_agui_events(kind: str, payload: dict[str, Any]) -> list[BaseEvent]:
    """Convertit un événement maison (kind, payload) en événements AG-UI."""
    run_id = str(payload.get("run_id") or "")

    if kind == "start":
        return [
            agui_events.RunStartedEvent(
                thread_id=run_id,
                run_id=run_id,
                input=RunAgentInput(
                    thread_id=run_id,
                    run_id=run_id,
                    messages=[
                        {
                            "role": "user",
                            "content": str(payload.get("question") or ""),
                            "id": f"msg-{uuid4().hex}",
                        }
                    ],
                ),
            )
        ]

    if kind == "answer":
        message_id = _text_message_id(payload)
        text = str(payload.get("text") or "")
        return [
            agui_events.TextMessageStartEvent(
                message_id=message_id,
                role="assistant",
            ),
            agui_events.TextMessageContentEvent(
                message_id=message_id,
                delta=text,
            ),
            agui_events.TextMessageEndEvent(message_id=message_id),
        ]

    if kind == "tool_call":
        tool_call_id = str(payload.get("tool_call_id") or f"call-{uuid4().hex}")
        return [
            agui_events.ToolCallStartEvent(
                tool_call_id=tool_call_id,
                tool_call_name=str(payload.get("name") or ""),
            ),
            agui_events.ToolCallArgsEvent(
                tool_call_id=tool_call_id,
                delta=json.dumps(payload.get("arguments") or {}, ensure_ascii=False),
            ),
        ]

    if kind == "done":
        return [
            agui_events.RunFinishedEvent(
                thread_id=run_id,
                run_id=run_id,
                result={
                    "status": payload.get("status"),
                    "turns": payload.get("turns"),
                    "cost_cents": payload.get("cost_cents"),
                },
            )
        ]

    if kind == "error":
        return [agui_events.RunErrorEvent(message=str(payload.get("message") or ""))]

    # Kind secondaire (ou inconnu) : CustomEvent nommé, aucune perte d'info.
    return [agui_events.CustomEvent(name=kind, value=payload)]


def format_agui_sse(
    kind: str, payload: dict[str, Any], state_event: BaseEvent | None = None
) -> str:
    """Sérialise les événements AG-UI en blocs SSE `data: {json}\n\n`.

    21a : si `state_event` est fourni (StateSnapshotEvent de l'accumulateur),
    il est émis après les événements du kind.
    """
    events = to_agui_events(kind, payload)
    if state_event is not None:
        events.append(state_event)
    return "".join(
        f"data: {event.model_dump_json(by_alias=True)}\n\n" for event in events
    )


# 21a : kinds qui alimentent les steps de l'état partagé (résumé court).
_STEP_KINDS = frozenset(
    {"llm_call", "tool_call", "guardrail", "a2a_route", "a2a_delegate", "a2a_event"}
)


class RunStateAccumulator:
    """21a : état partagé du run — un StateSnapshotEvent par event reçu.

    L'état est un JSON simple : {question, mode, run_id, status, agents, steps}.
    La boucle n'est pas modifiée : l'accumulateur vit côté sink (routes).
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "question": "",
            "mode": "",
            "run_id": "",
            "status": "running",
            "agents": [],
            "steps": [],
        }

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state, ensure_ascii=False))

    def _summary(self, kind: str, payload: dict[str, Any]) -> str:
        if kind == "tool_call":
            return f"tool {payload.get('name', '')}"
        if kind == "llm_call":
            return f"llm tour {payload.get('turn', '?')} · {payload.get('model', '')}"
        if kind == "guardrail":
            return f"garde-fou {payload.get('check', '')}"
        if kind == "a2a_route":
            agents = ", ".join(payload.get("agents", []))
            return f"route {payload.get('source', '')} → {agents}"
        if kind == "a2a_delegate":
            return (
                f"délégation {payload.get('agent', '')} ({payload.get('status', '')})"
            )
        if kind == "a2a_event":
            return f"{payload.get('agent', '')} · {payload.get('event_kind', '')}"
        return kind

    def event(
        self, kind: str, payload: dict[str, Any]
    ) -> agui_events.StateSnapshotEvent:
        """Met à jour l'état selon (kind, payload) et renvoie le snapshot AG-UI."""
        if kind == "start":
            self._state.update(
                question=str(payload.get("question") or ""),
                mode=str(payload.get("mode") or ""),
                run_id=str(payload.get("run_id") or ""),
                status="running",
                steps=[],
            )
        elif kind == "a2a_route":
            self._state["agents"] = list(payload.get("agents") or [])
        elif kind in ("done", "error"):
            self._state["status"] = str(payload.get("status") or "error")
        if kind in _STEP_KINDS:
            self._state["steps"].append(
                {"kind": kind, "summary": self._summary(kind, payload)}
            )
        return agui_events.StateSnapshotEvent(snapshot=self.snapshot())
