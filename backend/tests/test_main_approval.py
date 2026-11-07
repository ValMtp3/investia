"""Tests de l'endpoint POST /agent/runs/{run_id}/approval (spec 5.1).

Contrat : 200 + décision enregistrée quand le run est en attente ; 404 run inconnu ;
409 déjà décidé ; 422 body invalide. Le step « approval » est tracé en base.
"""

import asyncio
import json

import httpx
import pytest

from investia.agent.approval import ApprovalRegistry
from investia.llm.client import LlmResponse, ToolCall
from investia.main import create_app


class FakeLlm:
    """LLM fake qui appelle simulate_order au 1er tour puis répond (garde-fous ok)."""

    def __init__(self):
        self._first = True

    async def chat(self, model_key, messages, temperature=0.2, tools=None):
        if self._first:
            self._first = False
            return LlmResponse(
                content="",
                model="gpt-6-luna",
                prompt_tokens=10,
                completion_tokens=5,
                cost_cents=0.01,
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="simulate_order",
                        arguments={"symbol": "AAPL", "side": "buy", "quantity": 3},
                    )
                ],
            )
        return LlmResponse(
            content=(
                "## Thèse\nOrdre traité.\n\n## Risques\nvolatilité.\n\n"
                "## Confiance\n70\n\n## Sources\n- finnhub\n\n"
                "Simulation — pas un conseil en investissement.\n"
            ),
            model="gpt-6-luna",
            prompt_tokens=20,
            completion_tokens=50,
            cost_cents=0.02,
        )


class FakeMarket:
    async def get_quote(self, symbol):
        from datetime import UTC, datetime

        from investia.market.base import MarketData

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


class FakePortfolio:
    def __init__(self):
        self.orders: list[tuple[str, str, float]] = []

    async def get_portfolio(self):
        return {"cash": 10_000.0, "positions": [], "total_value": 10_000.0}

    async def place_order(self, symbol, side, quantity):
        self.orders.append((symbol, side, quantity))
        return {
            "order_id": "ord-1",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
        }

    async def adjust_capital(self, amount, reason):
        return {"cash": 10_000.0 + amount}


class FakeTraceStore:
    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.steps: list[tuple[str, int, str, dict]] = []
        self._next = 0

    async def start_run(self, question):
        self._next += 1
        run_id = f"00000000-0000-0000-0000-{self._next:012d}"
        self.runs[run_id] = {"question": question, "status": "running"}
        return run_id

    async def log_step(self, run_id, turn, kind, payload):
        self.steps.append((run_id, turn, kind, payload))

    async def finish_run(self, run_id, *, answer, model, turns, cost_cents, status):
        self.runs[run_id].update(status=status, answer=answer)

    async def list_runs(self, limit=50):
        return []

    async def get_run(self, run_id):
        run = self.runs.get(run_id)
        if run is None:
            return {"run": None, "steps": []}
        return {"run": {"id": run_id, **run}, "steps": []}


@pytest.fixture
def registry():
    return ApprovalRegistry()


@pytest.fixture
def trace_store():
    return FakeTraceStore()


@pytest.fixture
def portfolio():
    return FakePortfolio()


@pytest.fixture
def app(monkeypatch, trace_store, registry, portfolio):
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    return create_app(
        portfolio_service=portfolio,
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=trace_store,
        approval_registry=registry,
    )


async def parse_sse_events(response: httpx.Response) -> list[tuple[str, dict]]:
    events = []
    event_name = "message"
    async for chunk in response.aiter_text():
        for block in chunk.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
            if data_lines:
                events.append((event_name, json.loads("\n".join(data_lines))))
    return events


async def test_agent_run_stream_contains_approval_events(
    app, registry, trace_store, portfolio
):
    """Intégration SSE : /agent/run émet approval_request/approval et exécute l'ordre
    après décision. ASGITransport bufferise le flux : on décide via le registry
    directement (l'endpoint HTTP est couvert par les tests dédiés ci-dessous)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        stream_task = asyncio.create_task(
            client.post("/agent/run", json={"question": "achète 3 AAPL"})
        )
        # attend que la boucle ouvre l'attente d'approbation
        for _ in range(300):
            if trace_store.runs:
                break
            await asyncio.sleep(0.01)
        run_id = next(iter(trace_store.runs))
        for _ in range(300):
            if registry.has(run_id):
                break
            await asyncio.sleep(0.01)
        assert registry.has(run_id)
        assert await registry.decide(run_id, "approved") is True
        response = await asyncio.wait_for(stream_task, timeout=15)
        assert response.status_code == 200
        events = await parse_sse_events(response)
    kinds = [k for k, _ in events]
    assert "approval_request" in kinds
    assert "approval" in kinds
    assert kinds[-1] == "done"
    req = next(p for k, p in events if k == "approval_request")
    assert req["symbol"] == "AAPL" and req["side"] == "buy" and req["quantity"] == 3.0
    assert req["run_id"] == run_id
    approval = next(p for k, p in events if k == "approval")
    assert approval["decision"] == "approved"
    # l'ordre a été exécuté côté portefeuille
    assert portfolio.orders == [("AAPL", "buy", 3.0)]
    # la trace contient approval_request + approval
    step_kinds = [(k, p) for _, _, k, p in trace_store.steps]
    assert any(k == "approval_request" for k, _ in step_kinds)
    assert any(
        k == "approval" and p.get("decision") == "approved" for k, p in step_kinds
    )


async def test_approval_endpoint_200_when_pending(app, registry):
    run_id = "00000000-0000-0000-0000-000000000007"
    registry.open(run_id)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/agent/runs/{run_id}/approval", json={"decision": "approved"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok", "run_id": run_id, "decision": "approved"}
    # la décision a été poussée dans la file du run
    assert await registry.wait(run_id, timeout=0.1) == "approved"


async def _aiter_events(response: httpx.Response):
    event_name = "message"
    async for chunk in response.aiter_text():
        for block in chunk.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
            if data_lines:
                yield event_name, json.loads("\n".join(data_lines))


async def test_approval_endpoint_404_unknown_run(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/agent/runs/00000000-0000-0000-0000-000000000099/approval",
            json={"decision": "approved"},
        )
        assert resp.status_code == 404


async def test_approval_endpoint_422_invalid_body(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/agent/runs/00000000-0000-0000-0000-000000000001/approval",
            json={"decision": "peut-être"},
        )
        assert resp.status_code == 422


async def test_approval_endpoint_409_when_already_decided(app, registry):
    run_id = "00000000-0000-0000-0000-000000000042"
    registry.open(run_id)
    assert await registry.decide(run_id, "approved") is True
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/agent/runs/{run_id}/approval", json={"decision": "refused"}
        )
        assert resp.status_code == 409


async def test_approval_endpoint_422_invalid_uuid(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/agent/runs/pas-un-uuid/approval", json={"decision": "approved"}
        )
        assert resp.status_code == 422
