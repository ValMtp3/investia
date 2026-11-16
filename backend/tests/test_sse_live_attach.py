"""Tests TDD 23k : live-attach SSE via Redis pub/sub (run encore actif) + multi-agents.

Fallback : Redis KO -> event `detached` (comportement 23f inchangé).
"""

import asyncio
import json

import httpx
import pytest
from test_sse import FakeLlm, FakeMarket, FakePortfolio, FakeTraceStore, create_app
from test_sse_replay import parse_sse_with_ids

from investia.sse_live import (
    LiveAttachUnavailable,
    channel_for,
    live_attach,
    publish_event,
)


class FakePubSub:
    def __init__(self, fail_subscribe: bool = False):
        self.channels: list[str] = []
        self.fail_subscribe = fail_subscribe
        self.messages: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, channel: str):
        if self.fail_subscribe:
            raise ConnectionError("redis down")
        self.channels.append(channel)

    async def unsubscribe(self, channel: str):
        if channel in self.channels:
            self.channels.remove(channel)

    async def aclose(self):
        pass

    async def get_message(self, ignore_subscribe_messages=True, timeout=None):
        try:
            return await asyncio.wait_for(self.messages.get(), timeout)
        except TimeoutError:
            return None

    def feed(self, channel: str, data: str):
        self.messages.put_nowait({"type": "message", "channel": channel, "data": data})


class FakeRedis:
    def __init__(self, fail_subscribe: bool = False):
        self.published: list[tuple[str, str]] = []
        self._pubsub = FakePubSub(fail_subscribe)

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    def pubsub(self) -> FakePubSub:
        return self._pubsub


def test_channel_for():
    assert channel_for("abc") == "run:abc"


async def test_publish_event_json_sur_le_bon_canal():
    redis = FakeRedis()
    await publish_event(redis, "abc", 3, "answer", {"text": "salut"})
    channel, message = redis.published[0]
    assert channel == "run:abc"
    data = json.loads(message)
    assert data == {"seq": 3, "event": "answer", "payload": {"text": "salut"}}


async def test_publish_event_erreur_avalee():
    class KoRedis:
        async def publish(self, channel, message):
            raise ConnectionError("down")

    await publish_event(KoRedis(), "abc", 1, "start", {})  # ne lève pas


async def _collect(gen, limit=10):
    out = []
    async for item in gen:
        out.append(item)
        if len(out) >= limit:
            break
    return out


async def test_live_attach_filtre_dedup_et_stop_sur_done():
    redis = FakeRedis()
    ch = channel_for("r1")

    async def feeder():
        await asyncio.sleep(0.05)  # laisser le temps de s'abonner
        for seq, event in ((2, "answer"), (3, "answer"), (4, "done")):
            redis._pubsub.feed(
                ch, json.dumps({"seq": seq, "event": event, "payload": {}})
            )

    task = asyncio.create_task(feeder())
    events = await _collect(live_attach(redis, "r1", last_seq=2, idle_timeout=2.0))
    await task
    # seq 2 <= last_seq est ignoré (dédup), stop après done
    assert [e["seq"] for e in events] == [3, 4]
    assert events[-1]["event"] == "done"
    assert redis._pubsub.channels == []  # désabonné à la fin


async def test_live_attach_timeout_silence():
    redis = FakeRedis()
    events = await _collect(
        live_attach(redis, "r2", last_seq=0, idle_timeout=0.2, poll=0.05)
    )
    assert events == []  # silence -> arrêt propre, pas d'exception


async def test_live_attach_redis_ko_leve_unavailable():
    redis = FakeRedis(fail_subscribe=True)
    with pytest.raises(LiveAttachUnavailable):
        await _collect(live_attach(redis, "r3", last_seq=0, idle_timeout=0.2))


@pytest.fixture
def trace_store():
    return FakeTraceStore()


def _app(monkeypatch, trace_store, redis_client):
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    return create_app(
        portfolio_service=FakePortfolio(),
        llm=FakeLlm(),
        market=FakeMarket(),
        trace_store=trace_store,
        redis_client=redis_client,  # 23k
    )


async def test_replay_run_actif_live_attach_jusquau_done(monkeypatch, trace_store):
    """Run running + Redis OK : events stockés puis live, pas de detached."""
    redis = FakeRedis()
    app = _app(monkeypatch, trace_store, redis)
    run_id = "00000000-0000-0000-0000-000000000042"
    trace_store.runs[run_id] = {"question": "q", "status": "running", "steps": []}
    await trace_store.append_event(run_id, 1, "start", {"run_id": run_id})
    await trace_store.append_event(run_id, 2, "answer", {"text": "…"})

    ch = channel_for(run_id)

    async def feeder():
        # dès l'abonnement, le run publie la suite en live
        while ch not in redis._pubsub.channels:
            await asyncio.sleep(0.01)
        redis._pubsub.feed(ch, json.dumps({"seq": 3, "event": "answer", "payload": {}}))
        redis._pubsub.feed(
            ch, json.dumps({"seq": 4, "event": "done", "payload": {"ok": True}})
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = asyncio.create_task(feeder())
        async with client.stream(
            "POST",
            "/agent/run",
            json={"question": "q", "run_id": run_id},
            headers={"Last-Event-ID": "1"},
        ) as response:
            assert response.status_code == 200
            replayed = await parse_sse_with_ids(response)
        await task
    kinds = [k for _, k, _ in replayed]
    ids = [eid for eid, _, _ in replayed]
    assert ids == [2, 3, 4]  # stocké (2) puis live (3, 4)
    assert kinds == ["answer", "answer", "done"]
    assert "detached" not in kinds


async def test_replay_run_actif_redis_ko_emet_detached(monkeypatch, trace_store):
    """Fallback 23f : Redis KO -> replay stockés + detached, puis fin."""
    redis = FakeRedis(fail_subscribe=True)
    app = _app(monkeypatch, trace_store, redis)
    run_id = "00000000-0000-0000-0000-000000000043"
    trace_store.runs[run_id] = {"question": "q", "status": "running", "steps": []}
    await trace_store.append_event(run_id, 1, "start", {"run_id": run_id})
    await trace_store.append_event(run_id, 2, "answer", {"text": "…"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/agent/run",
            json={"question": "q", "run_id": run_id},
            headers={"Last-Event-ID": "1"},
        ) as response:
            replayed = await parse_sse_with_ids(response)
    kinds = [k for _, k, _ in replayed]
    assert kinds == ["answer", "detached"]  # fallback 23f inchangé


async def test_nouveau_run_publie_sur_redis_dans_le_sink(monkeypatch, trace_store):
    """Le sink publie chaque event sur run:<id>, même seq que la persistance."""
    redis = FakeRedis()
    app = _app(monkeypatch, trace_store, redis)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/agent/run", json={"question": "prix AAPL ?"}
        ) as response:
            events = await parse_sse_with_ids(response)
    run_id = next(p["run_id"] for _, k, p in events if k == "start")
    chans = {c for c, _ in redis.published}
    assert chans == {channel_for(run_id)}
    seqs_pub = sorted(
        json.loads(m)["seq"] for c, m in redis.published if c == channel_for(run_id)
    )
    assert seqs_pub == [e["seq"] for e in trace_store.events[run_id]]


async def test_replay_multi_agents_live_attach(monkeypatch, trace_store):
    """23k : la route /api/agents/run a aussi le replay + live-attach."""
    redis = FakeRedis()
    app = _app(monkeypatch, trace_store, redis)
    run_id = "00000000-0000-0000-0000-000000000044"
    trace_store.runs[run_id] = {"question": "q", "status": "running", "steps": []}
    await trace_store.append_event(run_id, 1, "start", {"run_id": run_id})
    ch = channel_for(run_id)

    async def feeder():
        while ch not in redis._pubsub.channels:
            await asyncio.sleep(0.01)
        redis._pubsub.feed(
            ch, json.dumps({"seq": 2, "event": "done", "payload": {"ok": True}})
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = asyncio.create_task(feeder())
        async with client.stream(
            "POST",
            "/api/agents/run",
            json={"question": "q", "run_id": run_id},
            headers={"Last-Event-ID": "0"},
        ) as response:
            assert response.status_code == 200
            replayed = await parse_sse_with_ids(response)
        await task
    kinds = [k for _, k, _ in replayed]
    assert kinds == ["start", "done"]  # stocké (1) + live (2)
    assert "detached" not in kinds
