"""23c : A2UI 1.0 (a2ui.org, Apache-2.0, announced 11/11/2026) — complément d'AG-UI.

L'agent émet des messages A2UI JSON (surfaceUpdate / dataModelUpdate /
beginRendering / deleteSurface + handshake {"version": "1.0"}) ; le client rend
avec SON propre catalogue de composants whitelisté. Sécurité héritée de 21b :
whitelist double (serveur + client), props littérales JSON validées (pydantic),
jamais de HTML brut ni de macros/DSL Express A2UI.

La boucle `run_agent` n'est pas modifiée : ce mapping vit côté sink, dans la
route POST /agent/run (paramètre `protocol=a2ui`).
"""

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

A2UI_CATALOG_ID = "investia-v1"
A2UI_VERSION_MESSAGE = {"version": "1.0"}

ALLOWED_MESSAGE_KEYS = frozenset(
    {"version", "surfaceUpdate", "dataModelUpdate", "beginRendering", "deleteSurface"}
)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-^_]{1,20}$")


class HistoryChartProps(BaseModel):
    """Props littérales du composant HistoryChart (catalogue client)."""

    model_config = {"extra": "forbid"}

    symbol: str
    days: int = Field(default=30, ge=1, le=365)

    @field_validator("symbol")
    @classmethod
    def _symbol_safe(cls, value: str) -> str:
        if not _SYMBOL_RE.match(value):
            raise ValueError(f"symbol invalide: {value!r}")
        return value


# Whitelist serveur outil -> (composant du catalogue, props depuis les arguments).
# Le frontend a sa propre whitelist : un composant inconnu y est ignoré.
A2UI_COMPONENT_BY_TOOL: dict[str, tuple[str, Any]] = {
    "get_history": (
        "HistoryChart",
        lambda args: HistoryChartProps(
            symbol=str(args.get("symbol") or ""),
            days=int(args.get("days") or 30),
        ).model_dump(),
    ),
}


class A2UIState:
    """Surfaces actives côté sink : elles sont supprimées au prochain `start`."""

    def __init__(self) -> None:
        self.surfaces: set[str] = set()

    def note_surface(self, surface_id: str) -> None:
        self.surfaces.add(surface_id)

    def drain_surfaces(self) -> list[str]:
        drained = sorted(self.surfaces)
        self.surfaces.clear()
        return drained


def _check_message(message: dict[str, Any]) -> dict[str, Any]:
    """Garde-fou de sortie : un seul type de message, toujours dans la whitelist."""
    keys = set(message)
    if len(keys) != 1 or next(iter(keys)) not in ALLOWED_MESSAGE_KEYS:
        raise ValueError(f"message A2UI invalide : {sorted(keys)}")
    return message


def to_a2ui_messages(
    kind: str, payload: dict[str, Any], state: A2UIState | None = None
) -> list[dict[str, Any]]:
    """Convertit un événement maison (kind, payload) en messages A2UI 1.0."""
    if kind == "start":
        messages: list[dict[str, Any]] = [dict(A2UI_VERSION_MESSAGE)]
        if state is not None:
            for surface_id in state.drain_surfaces():
                messages.append({"deleteSurface": {"surfaceId": surface_id}})
        return [_check_message(m) for m in messages]

    if kind == "tool_call":
        ui = A2UI_COMPONENT_BY_TOOL.get(str(payload.get("name") or ""))
        if ui is None:
            return []
        component, props_of = ui
        arguments = payload.get("arguments") or {}
        # Lève ValidationError si les props sont invalides (avant toute émission).
        props = props_of(arguments)
        tool_call_id = str(payload.get("tool_call_id") or "")
        surface_id = f"ui-{tool_call_id}"
        component_id = f"root-{tool_call_id}"
        if state is not None:
            state.note_surface(surface_id)
        return [
            _check_message(
                {
                    "surfaceUpdate": {
                        "surfaceId": surface_id,
                        "components": [
                            {"id": component_id, "type": component, "props": props}
                        ],
                    }
                }
            ),
            _check_message(
                {
                    "beginRendering": {
                        "surfaceId": surface_id,
                        "root": component_id,
                        "catalogId": A2UI_CATALOG_ID,
                    }
                }
            ),
        ]

    # A2UI ne transporte que l'UI déclarative ; le reste passe en legacy/agui.
    return []


def format_a2ui_sse(
    kind: str, payload: dict[str, Any], state: A2UIState | None = None
) -> str:
    """Sérialise les messages A2UI en blocs SSE `data: {json}\\n\\n`."""
    return "".join(
        f"data: {json.dumps(m, ensure_ascii=False)}\n\n"
        for m in to_a2ui_messages(kind, payload, state=state)
    )
