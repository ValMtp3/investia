"""Tests 17e — tool policy pré-schéma (OpenClaw) + double dial approval × sandbox
(Codex) : un outil refusé par la policy n'est pas envoyé au modèle (pas de schéma),
et SANDBOX_MODE=os sans backend d'isolation retire run_python pré-schéma."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from test_agent_loop import (
    FINAL_WITH_PRICE,
    FakeLlm,
    FakeMarket,
    make_response,
    quote_tool_call,
)
from test_sse import FakeTraceStore

from investia.agent import run_agent
from investia.config import Settings
from investia.market.base import MarketData
from investia.tools import build_tools
from investia.tools.policy import tool_policy_from_settings

QUESTION = "Quel est le prix de AAPL ?"

QUOTE = MarketData(
    value=344.63,
    currency="USD",
    source="finnhub",
    timestamp=datetime(2026, 10, 31, tzinfo=UTC),
)

MARKET_TOOL_NAMES = {"get_quote", "get_history", "get_indicators", "get_news"}


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": "postgresql://u:p@localhost/db",
        "redis_url": "redis://localhost:6379",
        "litellm_base_url": "http://litellm.test",
        "litellm_master_key": "sk-test",
        "app_secret_key": "x" * 32,
    }
    base.update(overrides)
    return Settings(**base)


def _tool_names(llm: FakeLlm, call_index: int = 0) -> set[str]:
    tools = llm.calls[call_index]["tools"] or []
    return {t["function"]["name"] for t in tools}


async def _run(policy, events: list):
    # scénario standard : un appel d'outil (get_quote) puis la réponse finale,
    # sinon les garde-fous bloquent une réponse avec prix sans source outil
    llm = FakeLlm(
        [
            make_response(content="je cherche", tool_calls=quote_tool_call()),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )

    async def sink(kind, payload):
        events.append((kind, payload))

    return await run_agent(
        QUESTION,
        llm,
        build_tools(FakeMarket(quote=QUOTE)),
        trace_store=FakeTraceStore(),
        event_sink=sink,
        tool_policy=policy,
    ), llm


# --- partie A : tool policy pré-schéma dans la boucle ---------------------------


async def test_tool_policy_set_filters_schemas_before_llm():
    events: list[tuple[str, dict]] = []
    (result, llm) = await _run({"get_quote"}, events)
    assert result.status == "ok"
    # le modèle n'a reçu QUE le schéma de get_quote, à chaque appel
    for i in range(len(llm.calls)):
        assert _tool_names(llm, i) == {"get_quote"}
    # event tool_policy tracé avec les outils retirés
    tp = next(p for k, p in events if k == "tool_policy")
    assert set(tp["kept"]) == {"get_quote"}
    assert set(tp["withheld"]) == MARKET_TOOL_NAMES - {"get_quote"}


async def test_tool_policy_none_keeps_all_tools():
    events: list[tuple[str, dict]] = []
    (result, llm) = await _run(None, events)
    assert result.status == "ok"
    assert _tool_names(llm) == MARKET_TOOL_NAMES
    tp = next(p for k, p in events if k == "tool_policy")
    assert tp["withheld"] == []
    assert set(tp["kept"]) == MARKET_TOOL_NAMES


async def test_tool_policy_callable_sync_and_async():
    events: list[tuple[str, dict]] = []
    (result, llm) = await _run(lambda name: name != "get_news", events)
    assert result.status == "ok"
    assert _tool_names(llm) == MARKET_TOOL_NAMES - {"get_news"}

    async def no_indicators(name: str) -> bool:
        return name != "get_indicators"

    (result2, llm2) = await _run(no_indicators, events)
    assert result2.status == "ok"
    assert _tool_names(llm2) == MARKET_TOOL_NAMES - {"get_indicators"}


# --- partie B : policy composée depuis la config (double dial) -------------------


def test_policy_from_settings_disabled_tools_csv():
    settings = _settings(disabled_tools="run_python, web_search", sandbox_mode="off")
    policy = tool_policy_from_settings(settings)
    assert policy is not None
    assert policy("run_python") is False
    assert policy("web_search") is False
    assert policy("get_quote") is True


def test_policy_from_settings_empty_returns_none():
    settings = _settings(disabled_tools="", sandbox_mode="off")
    assert tool_policy_from_settings(settings) is None


def test_policy_from_settings_sandbox_os_without_backend_disables_run_python():
    settings = _settings(sandbox_mode="os")
    policy = tool_policy_from_settings(settings, sandbox_available=False)
    assert policy is not None
    assert policy("run_python") is False
    assert policy("get_quote") is True
    # backend dispo -> run_python conservé
    assert tool_policy_from_settings(settings, sandbox_available=True) is None
    # SANDBOX_MODE=off -> jamais retiré pour cette raison
    settings_off = _settings(sandbox_mode="off")
    assert tool_policy_from_settings(settings_off, sandbox_available=False) is None


def test_settings_reject_invalid_dial_values():
    with pytest.raises(ValidationError):
        _settings(approval_mode="yes")
    with pytest.raises(ValidationError):
        _settings(sandbox_mode="maybe")
    assert _settings().approval_mode == "order"
    assert _settings().sandbox_mode == "os"
