"""Helpers SSE (Server-Sent Events) — zéro dépendance, StreamingResponse FastAPI."""

import json
from collections.abc import AsyncIterator
from typing import Any


def format_sse(event: str, payload: dict[str, Any]) -> str:
    """Un événement SSE : `event: <kind>\\ndata: <json>\\n\\n`."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def event_stream(
    generator: AsyncIterator[tuple[str, dict[str, Any]]],
) -> AsyncIterator[str]:
    async for event, payload in generator:
        yield format_sse(event, payload)
