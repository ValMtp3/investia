"""TDD étape 9 : spans OTel GenAI émis vers l'exporter (fake), liés au run_id.

Contrat : un appel LLM chat émet un span gen_ai.* (operation=chat, request.model,
usage tokens, cost) ; un appel d'outil émet un span tool.call (tool.name, ok) ;
les deux portent le run_id courant (ContextVar) ; une erreur LLM → status ERROR +
error.type ; sans run_id → run_id None, pas de crash ; sans init OTel → no-op.
"""

from datetime import UTC, datetime

import pytest

from investia.agent import run_agent
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools
from investia.tracing.otel import (
    InMemorySpanExporter,
    current_run_id,
    init_otel,
    reset_otel,
    start_chat_span,
    start_tool_span,
)


@pytest.fixture(autouse=True)
def otel():
    exporter = InMemorySpanExporter()
    init_otel(exporter=exporter)
    yield exporter
    reset_otel()


class FakeLlm:
    def __init__(self, error=None):
        self._error = error
        self.calls = 0

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        self.calls += 1
        if self._error:
            raise self._error
        return LlmResponse(
            content="ok",
            model="gpt-6-luna",
            prompt_tokens=10,
            completion_tokens=5,
            cost_cents=0.01,
            tool_calls=[
                ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
            ]
            if self.calls == 1
            else [],
        )


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 11, 7, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


class FakeTraceStore:
    def __init__(self):
        self._next = 0

    async def start_run(self, question):
        self._next += 1
        return f"run-{self._next}"

    async def log_step(self, *a, **k):
        pass

    async def finish_run(self, *a, **k):
        pass


FINAL = """## Thèse
AAPL vaut 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


async def test_chat_and_tool_spans_emitted_with_run_id(otel):
    # 1er appel = tool_call, 2e = réponse finale

    class TwoShotLlm(FakeLlm):
        async def chat(self, model_key, messages, temperature=0.2, tools=None):
            self.calls += 1
            if self.calls == 1:
                return LlmResponse(
                    content="",
                    model="gpt-6-luna",
                    prompt_tokens=10,
                    completion_tokens=5,
                    cost_cents=0.01,
                    tool_calls=[
                        ToolCall(
                            id="c1", name="get_quote", arguments={"symbol": "AAPL"}
                        )
                    ],
                )
            return LlmResponse(
                content=FINAL,
                model="gpt-6-luna",
                prompt_tokens=20,
                completion_tokens=50,
                cost_cents=0.02,
            )

    tools = build_tools(FakeMarket())
    result = await run_agent(
        "prix AAPL ?", TwoShotLlm(), tools, trace_store=FakeTraceStore()
    )
    assert result.turns == 2
    spans = otel.spans
    chat_spans = [s for s in spans if s["name"] == "gen_ai.chat"]
    tool_spans = [s for s in spans if s["name"] == "tool.call"]
    assert len(chat_spans) == 2
    assert len(tool_spans) == 1
    # run_id propagé via le ContextVar posé par run_agent
    assert all(s["run_id"] == "run-1" for s in spans)
    chat = chat_spans[0]
    assert chat["attributes"]["gen_ai.operation.name"] == "chat"
    assert chat["attributes"]["gen_ai.request.model"] == "gpt-6-luna"
    assert chat["attributes"]["gen_ai.usage.input_tokens"] == 10
    assert chat["attributes"]["gen_ai.usage.output_tokens"] == 5
    tool = tool_spans[0]
    assert tool["attributes"]["gen_ai.tool.name"] == "get_quote"
    assert tool["attributes"]["tool.ok"] is True


async def test_llm_error_marks_span_error(otel):
    with pytest.raises(RuntimeError):
        async with start_chat_span(model="gpt-6-luna", model_key="small"):
            raise RuntimeError("gateway down")
    (s,) = otel.spans
    assert s["status"] == "ERROR"
    assert s["attributes"]["error.type"] == "RuntimeError"


async def test_no_run_id_means_null_not_crash(otel):
    assert current_run_id.get() is None
    async with start_chat_span(model="m", model_key="small"):
        pass
    (s,) = otel.spans
    assert s["run_id"] is None


async def test_without_init_is_noop():
    reset_otel()
    async with start_chat_span(model="m", model_key="small"):
        pass  # ne doit rien lever
    async with start_tool_span(name="get_quote"):
        pass
