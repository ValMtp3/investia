"""Tests AG-UI (chantier 15c) : mapping des événements maison -> protocole AG-UI
et endpoint POST /agent/run?protocol=agui (SSE data-only, sans ligne `event:`)."""

import json

import httpx
import pytest
from ag_ui.core import events as agui_events
from test_sse import FakeLlm, FakeMarket, FakePortfolio, FakeTraceStore

from investia.agent.agui import to_agui_events
from investia.main import create_app


def _types(events):
    return [e.type for e in events]


# --- Mapping unitaire -------------------------------------------------------


def test_start_maps_to_run_started():
    events = to_agui_events(
        "start", {"run_id": "r1", "question": "prix AAPL ?", "model": "m"}
    )
    assert _types(events) == [agui_events.EventType.RUN_STARTED]
    event = events[0]
    assert isinstance(event, agui_events.RunStartedEvent)
    assert event.run_id == "r1"
    assert event.thread_id == "r1"
    assert event.input.messages[0].role == "user"
    assert event.input.messages[0].content == "prix AAPL ?"


def test_answer_maps_to_text_message_triplet_with_stable_message_id():
    events = to_agui_events("answer", {"text": "AAPL vaut 344.63 $", "run_id": "r1"})
    assert _types(events) == [
        agui_events.EventType.TEXT_MESSAGE_START,
        agui_events.EventType.TEXT_MESSAGE_CONTENT,
        agui_events.EventType.TEXT_MESSAGE_END,
    ]
    start, content, end = events
    assert isinstance(start, agui_events.TextMessageStartEvent)
    assert isinstance(content, agui_events.TextMessageContentEvent)
    assert isinstance(end, agui_events.TextMessageEndEvent)
    assert content.delta == "AAPL vaut 344.63 $"
    message_ids = {start.message_id, content.message_id, end.message_id}
    assert len(message_ids) == 1  # même message sur tout le triplet


def test_tool_call_maps_to_tool_call_start_then_args():
    events = to_agui_events(
        "tool_call",
        {"name": "get_quote", "arguments": {"symbol": "AAPL"}, "run_id": "r1"},
    )
    assert _types(events) == [
        agui_events.EventType.TOOL_CALL_START,
        agui_events.EventType.TOOL_CALL_ARGS,
    ]
    start, args = events
    assert isinstance(start, agui_events.ToolCallStartEvent)
    assert isinstance(args, agui_events.ToolCallArgsEvent)
    assert start.tool_call_name == "get_quote"
    assert start.tool_call_id == args.tool_call_id  # même appel d'outil
    assert json.loads(args.delta) == {"symbol": "AAPL"}


def test_done_maps_to_run_finished_with_result():
    events = to_agui_events(
        "done", {"status": "ok", "turns": 2, "cost_cents": 0.03, "run_id": "r1"}
    )
    assert _types(events) == [agui_events.EventType.RUN_FINISHED]
    event = events[0]
    assert isinstance(event, agui_events.RunFinishedEvent)
    assert event.run_id == "r1"
    assert event.thread_id == "r1"
    assert event.result["status"] == "ok"
    assert event.result["turns"] == 2
    assert event.result["cost_cents"] == 0.03


def test_error_maps_to_run_error():
    events = to_agui_events("error", {"message": "boom"})
    assert _types(events) == [agui_events.EventType.RUN_ERROR]
    assert isinstance(events[0], agui_events.RunErrorEvent)
    assert events[0].message == "boom"


@pytest.mark.parametrize(
    "kind",
    [
        "llm_call",
        "guardrail",
        "injection",
        "approval_request",
        "approval",
        "plan",
        "reflection",
        "consensus",
        "cache_hit",
    ],
)
def test_secondary_kinds_map_to_custom_event(kind):
    payload = {"run_id": "r1", "detail": "x"}
    events = to_agui_events(kind, payload)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, agui_events.CustomEvent)
    assert event.name == kind
    assert event.value == payload


def test_unknown_kind_maps_to_custom_event():
    events = to_agui_events("quelque_chose", {"a": 1})
    assert len(events) == 1
    assert isinstance(events[0], agui_events.CustomEvent)
    assert events[0].name == "quelque_chose"


def test_events_serialize_with_type_field_and_by_alias():
    events = to_agui_events("start", {"run_id": "r1", "question": "q"})
    payload = events[0].model_dump_json(by_alias=True)
    decoded = json.loads(payload)
    assert decoded["type"] == "RUN_STARTED"
    assert decoded["runId"] == "r1"


# --- API : POST /agent/run?protocol=agui ------------------------------------


@pytest.fixture
def trace_store():
    return FakeTraceStore()


@pytest.fixture
def app(monkeypatch, trace_store):
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
    ):
        monkeypatch.setenv(var, "x")
    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=trace_store,
    )


async def _read_raw_stream(client, url, body):
    async with client.stream("POST", url, json=body) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = ""
        async for chunk in response.aiter_text():
            raw += chunk
    return raw


def _parse_agui_blocks(raw):
    """Découpe le flux SSE en blocs `data: {...}\\n\\n` et décode le JSON AG-UI."""
    blocks = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        data_lines = [
            line[len("data:") :].strip()
            for line in block.splitlines()
            if line.startswith("data:")
        ]
        assert data_lines, f"bloc sans data: {block!r}"
        blocks.append(json.loads("\n".join(data_lines)))
    return blocks


async def test_agent_run_agui_protocol_emits_agui_events_without_event_lines(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        raw = await _read_raw_stream(
            client, "/agent/run?protocol=agui", {"question": "prix AAPL ?"}
        )
    assert "event:" not in raw  # AG-UI = data-only, le type est dans le JSON
    blocks = _parse_agui_blocks(raw)
    types = [b["type"] for b in blocks]
    assert types[0] == "RUN_STARTED"
    assert "TOOL_CALL_START" in types
    assert "TOOL_CALL_ARGS" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    assert types[-1] == "RUN_FINISHED"
    started = blocks[0]
    assert started["input"]["messages"][0]["content"] == "prix AAPL ?"
    finished = blocks[-1]
    assert finished["result"]["status"] == "ok"
    assert finished["result"]["turns"] >= 2
    content = next(b for b in blocks if b["type"] == "TEXT_MESSAGE_CONTENT")
    assert "344.63" in content["delta"]
    # Les kinds secondaires passent en CustomEvent nommé
    custom_names = [b["name"] for b in blocks if b["type"] == "CUSTOM"]
    assert "llm_call" in custom_names


async def test_agent_run_default_protocol_stays_legacy(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        raw = await _read_raw_stream(client, "/agent/run", {"question": "prix AAPL ?"})
    assert "event: start" in raw
    assert "event: done" in raw
    assert '"type": "RUN_STARTED"' not in raw
