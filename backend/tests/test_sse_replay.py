"""Tests TDD 23f : SSE replay Last-Event-ID (ids, persistance, re-POST)."""

import json

import httpx
import pytest
from test_sse import FakeLlm, FakeMarket, FakePortfolio, FakeTraceStore, create_app


def test_format_sse_emet_id_quand_fourni():
    from investia.sse import format_sse

    bloc = format_sse("answer", {"text": "salut"}, event_id=3)
    assert bloc.startswith("id: 3\n")
    assert "event: answer\n" in bloc
    assert 'data: {"text": "salut"}\n\n' in bloc
    # rétrocompatible : sans event_id, pas de ligne id:
    assert "id:" not in format_sse("answer", {"text": "salut"})


async def parse_sse_with_ids(response: httpx.Response) -> list[tuple[int, str, dict]]:
    """Parse un flux SSE en capturant (id, event, data)."""
    events = []
    event_id = 0
    name = "message"
    async for chunk in response.aiter_text():
        for block in chunk.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            data_lines = []
            for line in block.splitlines():
                if line.startswith("id:"):
                    event_id = int(line[len("id:") :].strip())
                elif line.startswith("event:"):
                    name = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
            if data_lines:
                events.append((event_id, name, json.loads("\n".join(data_lines))))
    return events


@pytest.fixture
def trace_store():
    return FakeTraceStore()


@pytest.fixture
def app(monkeypatch, trace_store):
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=trace_store,
    )


async def _run_once(client, question="prix AAPL ?"):
    async with client.stream(
        "POST", "/agent/run", json={"question": question}
    ) as response:
        assert response.status_code == 200
        events = await parse_sse_with_ids(response)
    return events


async def test_nouveau_run_emet_des_ids_sequentiels_et_persiste(app, trace_store):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _run_once(client)
    ids = [eid for eid, _, _ in events]
    assert ids == list(range(1, len(ids) + 1))  # id: 1..N, séquentiel
    run_id = next(p["run_id"] for _, k, p in events if k == "start")
    stored = trace_store.events[run_id]
    assert [e["seq"] for e in stored] == ids  # persisté dans le même ordre
    assert [e["event"] for e in stored] == [k for _, k, _ in events]


async def test_replay_avec_last_event_id_ne_renvoie_que_la_suite(app, trace_store):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _run_once(client)
        run_id = next(p["run_id"] for _, k, p in events if k == "start")
        total = len(events)
        assert total > 2
        async with client.stream(
            "POST",
            "/agent/run",
            json={"question": "prix AAPL ?", "run_id": run_id},
            headers={"Last-Event-ID": "2"},
        ) as response:
            assert response.status_code == 200
            replayed = await parse_sse_with_ids(response)
    # uniquement seq > 2, avec les bons ids, et le run terminé -> pas de detached
    assert [eid for eid, _, _ in replayed] == list(range(3, total + 1))
    assert [k for _, k, _ in replayed] == [k for _, k, _ in events[2:]]
    assert all(k != "detached" for _, k, _ in replayed)
    assert replayed[-1][1] == "done"


async def test_replay_sans_last_event_id_rejoue_depuis_le_debut(app, trace_store):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _run_once(client)
        run_id = next(p["run_id"] for _, k, p in events if k == "start")
        async with client.stream(
            "POST", "/agent/run", json={"question": "q", "run_id": run_id}
        ) as response:
            replayed = await parse_sse_with_ids(response)
    assert [eid for eid, _, _ in replayed] == [eid for eid, _, _ in events]


async def test_replay_run_inconnu_404_et_run_id_invalide_422(app, trace_store):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/run",
            json={"question": "q", "run_id": "00000000-0000-0000-0000-000000009999"},
        )
        assert response.status_code == 404
        response = await client.post(
            "/agent/run", json={"question": "q", "run_id": "pas-un-uuid"}
        )
        assert response.status_code == 422


async def test_replay_run_encore_actif_emet_detached(app, trace_store):
    """Run status=running avec 2 events stockés -> replay + event detached, puis fin."""
    run_id = "00000000-0000-0000-0000-000000000042"
    trace_store.runs[run_id] = {"question": "q", "status": "running", "steps": []}
    await trace_store.append_event(run_id, 1, "start", {"run_id": run_id})
    await trace_store.append_event(run_id, 2, "answer", {"turn": 1, "text": "…"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/agent/run",
            json={"question": "q", "run_id": run_id},
            headers={"Last-Event-ID": "1"},
        ) as response:
            assert response.status_code == 200
            replayed = await parse_sse_with_ids(response)
    kinds = [k for _, k, _ in replayed]
    assert kinds == ["answer", "detached"]  # seq 2 rejoué, puis detached
    assert replayed[-1][2]["run_id"] == run_id


@pytest.mark.integration
async def test_integration_run_events_roundtrip_pgvector():
    """append_event + events_after sur la vraie table run_events (migration 0013)."""
    from investia.db import get_session
    from investia.tracing.store import DbTraceStore

    store = DbTraceStore(get_session())
    run_id = "00000000-0000-0000-0000-000000000777"
    await store.start_run("q test replay")
    for seq in (1, 2, 3):
        await store.append_event(run_id, seq, "answer", {"seq": seq})
    after = await store.events_after(run_id, 1)
    assert [e["seq"] for e in after] == [2, 3]
    assert after[0]["payload"] == {"seq": 2}
