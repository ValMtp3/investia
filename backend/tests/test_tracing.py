"""Tests du TraceStore (fake en mémoire) et de l'intégration boucle -> traces."""

from datetime import UTC, datetime

from investia.agent import run_agent
from investia.llm.client import LlmResponse, ToolCall
from investia.market.base import MarketData
from investia.tools import build_tools


class FakeStore:
    def __init__(self):
        self.runs = {}
        self.steps = []

    async def start_run(self, question: str):
        run_id = f"run-{len(self.runs) + 1}"
        self.runs[run_id] = {"question": question, "status": "running"}
        return run_id

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append(
            {"run_id": run_id, "turn": turn, "kind": kind, "payload": payload}
        )

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.runs[run_id].update(
            answer=answer,
            model=model,
            turns=turns,
            cost_cents=cost_cents,
            status=status,
        )


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


FINAL_OK = """## Thèse
AAPL vaut 344.63 $.

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


def resp(content="", tool_calls=None):
    return LlmResponse(
        content=content,
        model="gpt-6-luna",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=0.01,
        tool_calls=tool_calls or [],
    )


async def test_run_is_traced_end_to_end_with_fake_store():
    store = FakeStore()
    llm = FakeLlm(
        [
            resp(
                "",
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            ),
            resp(FINAL_OK),
        ]
    )
    result = await run_agent(
        "prix AAPL ?", llm, build_tools(FakeMarket()), trace_store=store
    )
    run_id = next(iter(store.runs))
    run = store.runs[run_id]
    assert run["status"] == "ok"
    assert run["turns"] == result.turns
    assert run["answer"] == result.answer
    kinds = [s["kind"] for s in store.steps]
    assert "llm_call" in kinds
    assert "tool_call" in kinds
    assert "guardrail" in kinds
    tool_step = next(s for s in store.steps if s["kind"] == "tool_call")
    assert tool_step["payload"]["name"] == "get_quote"
    assert "344.63" in tool_step["payload"]["result"]


async def test_blocked_run_has_status_blocked():
    store = FakeStore()
    bad = FINAL_OK.replace("344.63", "999999")
    llm = FakeLlm(
        [
            resp(
                "",
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            ),
            resp(bad),
            resp(bad),
            resp(bad),
        ]
    )
    await run_agent(
        "prix AAPL ?",
        llm,
        build_tools(FakeMarket()),
        trace_store=store,
        max_corrections=2,
    )
    run = next(iter(store.runs.values()))
    assert run["status"] == "blocked"


async def test_no_secret_leaks_into_trace_payloads():
    store = FakeStore()
    llm = FakeLlm(
        [
            resp(
                "",
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ],
            ),
            resp(FINAL_OK),
        ]
    )
    await run_agent("prix AAPL ?", llm, build_tools(FakeMarket()), trace_store=store)
    import json

    blob = json.dumps(store.steps) + json.dumps(store.runs)
    assert "sk-" not in blob, "aucune clé API dans les traces"
    assert "Bearer" not in blob
