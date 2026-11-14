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


def format_agui_sse(kind: str, payload: dict[str, Any]) -> str:
    """Sérialise les événements AG-UI en blocs SSE `data: {json}\n\n`."""
    return "".join(
        f"data: {event.model_dump_json(by_alias=True)}\n\n"
        for event in to_agui_events(kind, payload)
    )
