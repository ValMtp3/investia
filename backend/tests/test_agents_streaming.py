"""Tests 20c — streaming A2A intermédiaire : caller + executors (artifacts "step").

Contrat : HttpA2ACaller.call(agent, text, on_event=cb) forward chaque artifact
A2A nommé "step" (JSON {"kind","payload"}) vers cb, et retourne toujours
l'artifact final. Côté executor, le sink des events du harness émet des
artifacts "step" dans la EventQueue (l'artifact final métier reste last_chunk).
"""

import json
from typing import Any, cast

from a2a.types import Artifact, Part, StreamResponse, TaskArtifactUpdateEvent

from investia.agents.orchestrator import HttpA2ACaller, _extract_step_event


def _artifact_event(name: str, text: str, last_chunk: bool = False) -> StreamResponse:
    return StreamResponse(
        artifact_update=TaskArtifactUpdateEvent(
            task_id="t",
            context_id="c",
            artifact=Artifact(artifact_id="a", name=name, parts=[Part(text=text)]),
            last_chunk=last_chunk,
        )
    )


def test_extract_step_event_artifact_step():
    ev = _artifact_event("step", json.dumps({"kind": "tool_call", "payload": {"n": 1}}))
    assert _extract_step_event(ev) == ("tool_call", {"n": 1})


def test_extract_step_event_ignore_artifact_final_et_non_json():
    final = _artifact_event("analysis", '{"analysis": "..."}', last_chunk=True)
    assert _extract_step_event(final) is None
    step = _artifact_event("step", "pas du json")
    assert _extract_step_event(step) is None
    step2 = _artifact_event("step", '{"kind": "llm_call"}')  # payload manquant
    assert _extract_step_event(step2) == ("llm_call", {})


class _FakeA2AClient:
    """Client A2A fake : send_message itère une liste de StreamResponse."""

    def __init__(self, events):
        self._events = list(events)

    async def send_message(self, request):
        for ev in self._events:
            yield ev


async def test_http_caller_forwards_step_events_and_returns_final(monkeypatch):
    """20c : on_event reçoit chaque artifact "step" ; le retour = artifact final."""
    events = [
        _artifact_event(
            "step", json.dumps({"kind": "llm_call", "payload": {"turn": 1}})
        ),
        _artifact_event(
            "step", json.dumps({"kind": "tool_call", "payload": {"name": "get_quote"}})
        ),
        _artifact_event("analysis", '{"analysis": "résultat"}', last_chunk=True),
    ]

    async def fake_create_client(url):
        return _FakeA2AClient(events)

    monkeypatch.setattr("a2a.client.create_client", fake_create_client)
    received: list[tuple[str, dict]] = []

    async def on_event(kind, payload):
        received.append((kind, payload))

    caller = HttpA2ACaller(base_url="http://test")
    result = await caller.call("analyste", "question", on_event=on_event)
    assert received == [
        ("llm_call", {"turn": 1}),
        ("tool_call", {"name": "get_quote"}),
    ]
    assert result == {"analysis": "résultat"}


async def test_http_caller_sans_on_event_ne_leve_pas(monkeypatch):
    """Zéro régression : sans on_event, call retourne juste l'artifact final."""
    events = [
        _artifact_event("step", json.dumps({"kind": "llm_call", "payload": {}})),
        _artifact_event("answer", '{"answer": "ok"}', last_chunk=True),
    ]

    async def fake_create_client(url):
        return _FakeA2AClient(events)

    monkeypatch.setattr("a2a.client.create_client", fake_create_client)
    caller = HttpA2ACaller(base_url="http://test")
    result = await caller.call("redacteur", "q")
    assert result == {"answer": "ok"}


# --- executors : le sink du harness émet des artifacts "step" ------------------


class _FakeEventQueue:
    def __init__(self):
        self.events: list = []

    async def enqueue_event(self, event):
        self.events.append(event)


def test_emit_step_artifact_payload_json():
    """20c : la traduction event harness -> artifact "step" produit le JSON attendu."""
    from investia.agents.executors import _step_artifact

    artifact = _step_artifact("tool_call", {"name": "get_quote", "ok": True})
    assert artifact.name == "step"
    payload = json.loads(artifact.parts[0].text)
    assert payload == {
        "kind": "tool_call",
        "payload": {"name": "get_quote", "ok": True},
    }


async def test_executor_analyste_emet_steps_puis_artifact_final():
    """20c : l'analyste streame les events du harness avant l'artifact final."""
    from a2a.server.agent_execution.context import RequestContext
    from a2a.types import Message, SendMessageRequest
    from a2a.types import Part as A2APart
    from test_agents_a2a import FakeLlm, FakeMarket, FakePortfolio

    from investia.agents.executors import AnalysteExecutor
    from investia.tools import build_tools

    queue = _FakeEventQueue()
    context = RequestContext(
        call_context=cast(Any, None),
        request=SendMessageRequest(
            message=Message(
                role="ROLE_USER", parts=[A2APart(text="analyse AAPL")], message_id="m1"
            )
        ),
        task_id="t1",
        context_id="c1",
    )
    executor = AnalysteExecutor(
        FakeLlm(), build_tools(FakeMarket(), portfolio_service=FakePortfolio())
    )
    await executor.execute(context, cast(Any, queue))

    artifacts = [ev.artifact for ev in queue.events if getattr(ev, "artifact", None)]
    steps = [a for a in artifacts if a.name == "step"]
    finals = [a for a in artifacts if a.name != "step"]
    assert steps, "aucun artifact step émis"
    for s in steps:
        parsed = json.loads(s.parts[0].text)
        assert set(parsed) == {"kind", "payload"}
    assert len(finals) == 1 and finals[0].name == "analysis"
    assert "344.63" in finals[0].parts[0].text
