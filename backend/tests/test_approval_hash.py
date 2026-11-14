"""Tests du hash d'approbation HITL (spec 13d) — écrits AVANT le code.

Contrat : l'approbation est liée au hash SHA-256 exact du payload affiché
(anti « replan-after-yes ») ; decide() refuse (False) si le hash fourni diffère
du hash de la demande en attente ; la boucle re-vérifie avant d'exécuter.
"""

import asyncio
import hashlib
import json

import httpx
import pytest
from test_agent_approval import (
    FINAL_OK,
    FakeLlm,
    FakeMarket,
    FakePortfolioService,
    FakeTraceStore,
    make_response,
    order_tool_call,
)
from test_main_approval import FakePortfolio

from investia.agent import run_agent
from investia.agent.approval import ApprovalRegistry, payload_hash_for
from investia.main import create_app

RUN_ID = "00000000-0000-0000-0000-000000000042"


# ------------------------------------------------------------- hash


def test_payload_hash_est_sha256_canonique():
    expected = hashlib.sha256(
        json.dumps(
            {"quantity": 3.0, "side": "buy", "symbol": "AAPL"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert payload_hash_for("AAPL", "buy", 3.0) == expected
    assert len(payload_hash_for("AAPL", "buy", 3.0)) == 64


def test_payload_hash_stable_et_sensible_aux_args():
    assert payload_hash_for("aapl", "buy", 3.0) == payload_hash_for("AAPL", "buy", 3.0)
    assert payload_hash_for("AAPL", "buy", 3.0) != payload_hash_for("AAPL", "buy", 4.0)
    assert payload_hash_for("AAPL", "buy", 3.0) != payload_hash_for("AAPL", "sell", 3.0)


# ------------------------------------------------------------- registry


async def test_decide_avec_mauvais_hash_est_refuse():
    registry = ApprovalRegistry()
    registry.open(RUN_ID, payload_hash="a" * 64)
    assert await registry.decide(RUN_ID, "approved", "b" * 64) is False
    # la décision n'a pas été enregistrée : on peut encore décider avec le bon hash
    assert await registry.decide(RUN_ID, "approved", "a" * 64) is True
    assert await registry.wait(RUN_ID, timeout=0.1) == "approved"
    assert registry.approved_hash(RUN_ID) == "a" * 64


async def test_decide_sans_hash_reste_retrocompatible():
    registry = ApprovalRegistry()
    registry.open("run-sans-hash")
    assert await registry.decide("run-sans-hash", "approved") is True
    registry.open("run-hash-mais-pas-fourni", payload_hash="c" * 64)
    assert await registry.decide("run-hash-mais-pas-fourni", "refused") is True


# ------------------------------------------------------------- boucle


async def test_approval_request_contient_le_hash_et_ordre_exécute_si_hash_ok():
    portfolio = FakePortfolioService()
    registry = ApprovalRegistry()
    store = FakeTraceStore()
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    llm = FakeLlm(
        [make_response(tool_calls=order_tool_call()), make_response(content=FINAL_OK)]
    )
    from investia.tools import build_tools

    tools = build_tools(FakeMarket(), portfolio_service=portfolio)

    task = asyncio.create_task(
        run_agent(
            "achète 3 AAPL",
            llm,
            tools,
            trace_store=store,
            event_sink=sink,
            approval_registry=registry,
            approval_timeout=5.0,
        )
    )
    for _ in range(100):
        if store.runs:
            break
        await asyncio.sleep(0.01)
    run_id = next(iter(store.runs))
    for _ in range(100):
        if registry.has(run_id):
            break
        await asyncio.sleep(0.01)
    req = next(p for k, p in events if k == "approval_request")
    assert req["payload_hash"] == payload_hash_for("AAPL", "buy", 3.0)
    # le step tracé contient aussi le hash
    assert any(
        k == "approval_request" and p.get("payload_hash") == req["payload_hash"]
        for _, _, k, p in store.steps
    )
    assert await registry.decide(run_id, "approved", req["payload_hash"]) is True
    await task
    assert portfolio.orders == [("AAPL", "buy", 3.0)]


class TamperedRegistry(ApprovalRegistry):
    """Simule un payload modifié après approbation (hash approuvé != hash exécuté)."""

    def approved_hash(self, run_id: str) -> str | None:
        return "0" * 64  # hash différent de celui de la demande


async def test_hash_modifie_apres_approbation_annule_ordre():
    portfolio = FakePortfolioService()
    registry = TamperedRegistry()
    store = FakeTraceStore()
    events: list[tuple[str, dict]] = []

    async def sink(kind, payload):
        events.append((kind, payload))

    llm = FakeLlm(
        [make_response(tool_calls=order_tool_call()), make_response(content=FINAL_OK)]
    )
    from investia.tools import build_tools

    tools = build_tools(FakeMarket(), portfolio_service=portfolio)
    task = asyncio.create_task(
        run_agent(
            "achète 3 AAPL",
            llm,
            tools,
            trace_store=store,
            event_sink=sink,
            approval_registry=registry,
            approval_timeout=5.0,
        )
    )
    for _ in range(100):
        if store.runs:
            break
        await asyncio.sleep(0.01)
    run_id = next(iter(store.runs))
    for _ in range(100):
        if registry.has(run_id):
            break
        await asyncio.sleep(0.01)
    req = next(p for k, p in events if k == "approval_request")
    await registry.decide(run_id, "approved", req["payload_hash"])
    await task
    # aucun ordre exécuté : le hash approuvé ne correspond pas au payload exécuté
    assert portfolio.orders == []
    tool_messages = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "modifié après approbation" in tool_messages[0]["content"]


# ------------------------------------------------------------- endpoint


@pytest.fixture
def app_et_registry(monkeypatch):
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    from test_main_approval import FakeLlm as AppFakeLlm
    from test_main_approval import FakeMarket as AppFakeMarket

    registry = ApprovalRegistry()
    app = create_app(
        portfolio_service=FakePortfolio(),
        llm=AppFakeLlm(),
        market=AppFakeMarket(),
        trace_store=FakeTraceStore(),
        approval_registry=registry,
    )
    return app, registry


async def test_endpoint_409_si_payload_hash_incoherent(app_et_registry):
    app, registry = app_et_registry
    registry.open(RUN_ID, payload_hash="a" * 64)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/agent/runs/{RUN_ID}/approval",
            json={"decision": "approved", "payload_hash": "b" * 64},
        )
        assert resp.status_code == 409
        # la décision n'a pas été enregistrée : le bon hash passe encore
        resp2 = await client.post(
            f"/agent/runs/{RUN_ID}/approval",
            json={"decision": "approved", "payload_hash": "a" * 64},
        )
        assert resp2.status_code == 200


async def test_endpoint_payload_hash_optionnel_retrocompatible(app_et_registry):
    """Sans payload_hash dans le body : pas de 422, comportement 5.1 inchangé."""
    app, registry = app_et_registry
    registry.open(RUN_ID, payload_hash="a" * 64)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/agent/runs/{RUN_ID}/approval", json={"decision": "approved"}
        )
        assert resp.status_code == 200
        assert await registry.wait(RUN_ID, timeout=0.1) == "approved"
