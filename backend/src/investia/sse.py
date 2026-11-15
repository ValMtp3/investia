"""Helpers SSE (Server-Sent Events) — zéro dépendance, StreamingResponse FastAPI."""

import json
from collections.abc import AsyncIterator
from typing import Any


def format_sse(event: str, payload: dict[str, Any], event_id: int | None = None) -> str:
    """Un événement SSE : `event: <kind>\\ndata: <json>\\n\\n`.

    23f : avec `event_id`, une ligne `id: <seq>` précède l'event — c'est ce que
    le navigateur renvoie en `Last-Event-ID` à la reconnexion (replay SSE).
    """
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    data = json.dumps(payload, ensure_ascii=False)
    return f"{id_line}event: {event}\ndata: {data}\n\n"


async def event_stream(
    generator: AsyncIterator[tuple[str, dict[str, Any]]],
) -> AsyncIterator[str]:
    async for event, payload in generator:
        yield format_sse(event, payload)
