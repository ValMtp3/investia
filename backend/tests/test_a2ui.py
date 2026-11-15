"""Tests 23c — A2UI 1.0 (complément d'AG-UI, P9.4) : messages déclaratifs
surfaceUpdate/beginRendering/deleteSurface, whitelist serveur, props littérales
validées (jamais de HTML brut ni macros DSL).

TDD : écrits AVANT backend/src/investia/agent/a2ui.py et le câblage route.
"""

import json

import pytest
from pydantic import ValidationError

from investia.agent.a2ui import (
    A2UI_CATALOG_ID,
    A2UIState,
    _check_message,
    format_a2ui_sse,
    to_a2ui_messages,
)


def _state() -> A2UIState:
    return A2UIState()


def test_start_emet_handshake_version():
    msgs = to_a2ui_messages(
        "start", {"run_id": "r1", "question": "q ?"}, state=_state()
    )
    assert msgs[0] == {"version": "1.0"}


def test_start_nettoie_les_surfaces_du_run_precedent():
    state = _state()
    state.note_surface("ui-c0")
    msgs = to_a2ui_messages("start", {"run_id": "r2"}, state=state)
    deletes = [m["deleteSurface"]["surfaceId"] for m in msgs if "deleteSurface" in m]
    assert deletes == ["ui-c0"]
    assert state.surfaces == set()


def test_tool_call_get_history_emet_surface_update_et_begin_rendering():
    msgs = to_a2ui_messages(
        "tool_call",
        {
            "name": "get_history",
            "tool_call_id": "c1",
            "arguments": {"symbol": "AAPL", "days": 30},
        },
        state=_state(),
    )
    surface = next(m["surfaceUpdate"] for m in msgs if "surfaceUpdate" in m)
    begin = next(m["beginRendering"] for m in msgs if "beginRendering" in m)
    comp = surface["components"][0]
    assert comp["type"] == "HistoryChart"  # nom du catalogue client
    assert comp["props"] == {"symbol": "AAPL", "days": 30}
    assert surface["surfaceId"] == begin["surfaceId"] == "ui-c1"
    assert begin["root"] == comp["id"]
    assert begin["catalogId"] == A2UI_CATALOG_ID


def test_tool_call_non_whiteliste_nemet_rien():
    msgs = to_a2ui_messages(
        "tool_call",
        {"name": "get_quote", "tool_call_id": "c9", "arguments": {"symbol": "AAPL"}},
        state=_state(),
    )
    assert msgs == []


def test_autre_kind_nemet_rien():
    assert to_a2ui_messages("llm_call", {"turn": 1}, state=_state()) == []
    assert to_a2ui_messages("answer", {"text": "x"}, state=_state()) == []


def test_props_invalides_rejetees_avant_emission():
    # symbol avec HTML → rejeté (props littérales sûres uniquement)
    with pytest.raises(ValidationError):
        to_a2ui_messages(
            "tool_call",
            {
                "name": "get_history",
                "tool_call_id": "c2",
                "arguments": {"symbol": "<script>alert(1)</script>", "days": 30},
            },
            state=_state(),
        )
    # days hors bornes → rejeté
    with pytest.raises(ValidationError):
        to_a2ui_messages(
            "tool_call",
            {
                "name": "get_history",
                "tool_call_id": "c3",
                "arguments": {"symbol": "AAPL", "days": 9999},
            },
            state=_state(),
        )


def test_check_message_rejete_un_type_inconnu():
    with pytest.raises(ValueError):
        _check_message({"evil": {"x": 1}})
    with pytest.raises(ValueError):
        _check_message({"surfaceUpdate": {}, "beginRendering": {}})  # 2 clés
    assert _check_message({"deleteSurface": {"surfaceId": "ui-x"}}) == {
        "deleteSurface": {"surfaceId": "ui-x"}
    }


def test_format_a2ui_sse_blocs_data_json():
    out = format_a2ui_sse(
        "tool_call",
        {"name": "get_history", "tool_call_id": "c1", "arguments": {"symbol": "AAPL"}},
        state=_state(),
    )
    blocks = [b for b in out.split("\n\n") if b]
    assert all(b.startswith("data: ") for b in blocks)
    msgs = [json.loads(b[len("data: ") :]) for b in blocks]
    assert any("surfaceUpdate" in m for m in msgs)
    assert any("beginRendering" in m for m in msgs)


# --- API : POST /agent/run?protocol=a2ui ------------------------------------

import httpx  # noqa: E402
from test_agui import FakeMarket, FakePortfolio, FakeTraceStore  # noqa: E402
from test_injection import FINAL_OK  # noqa: E402
from test_sse import create_app  # noqa: E402

from investia.llm.client import LlmResponse, ToolCall  # noqa: E402


class FakeLlmHistory:
    """FakeLlm : get_quote (chiffres sourcés) puis get_history (surface A2UI)."""

    def __init__(self):
        self._responses = [
            LlmResponse(
                content="",
                model="gpt-6-luna",
                prompt_tokens=10,
                completion_tokens=5,
                cost_cents=0.01,
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"}),
                    ToolCall(
                        id="c2",
                        name="get_history",
                        arguments={"symbol": "AAPL", "days": 90},
                    ),
                ],
            ),
            LlmResponse(
                content=FINAL_OK,
                model="gpt-6-luna",
                prompt_tokens=20,
                completion_tokens=50,
                cost_cents=0.02,
            ),
        ]

    async def chat(
        self, model_key, messages, temperature=0.2, tools=None, logprobs=False
    ):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


@pytest.fixture
def app(monkeypatch):
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlmHistory(),
        market=FakeMarket(),
        trace_store=FakeTraceStore(),
    )


async def test_agent_run_a2ui_protocol_emits_a2ui_messages(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/agent/run?protocol=a2ui", json={"question": "prix AAPL ?"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            raw = ""
            async for chunk in response.aiter_text():
                raw += chunk
    assert "event:" not in raw  # A2UI = data-only
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
        if data_lines:
            blocks.append(json.loads("\n".join(data_lines)))
    # handshake de version en premier bloc
    assert blocks[0] == {"version": "1.0"}
    # le run fait un get_history → surface A2UI émise
    surfaces = [b["surfaceUpdate"] for b in blocks if "surfaceUpdate" in b]
    assert surfaces, f"aucune surfaceUpdate dans {blocks}"
    comp = surfaces[0]["components"][0]
    assert comp["type"] == "HistoryChart"
    assert comp["props"] == {"symbol": "AAPL", "days": 90}
    begins = [b["beginRendering"] for b in blocks if "beginRendering" in b]
    assert begins and begins[0]["catalogId"] == A2UI_CATALOG_ID


async def test_agent_run_legacy_protocol_inchange(app):
    """Zéro régression : protocol par défaut = legacy (`event:` présent)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/agent/run", json={"question": "prix AAPL ?"}
        ) as response:
            raw = ""
            async for chunk in response.aiter_text():
                raw += chunk
    assert "event:" in raw
    assert '"version": "1.0"' not in raw
