"""Tests du module redaction (spec 13a) et du TraceStore redacteur.

TDD : ces tests ont été écrits AVANT backend/src/investia/redaction.py.
"""

import json

from investia.redaction import (
    REDACTED,
    ChainRedactor,
    PresidioRedactor,
    RegexRedactor,
    default_redactor,
    env_secret_values,
    redact_value,
)
from investia.tracing.store import DbTraceStore

RUN_ID = "00000000-0000-0000-0000-000000000001"


def test_env_secret_values_reads_only_secret_like_env(monkeypatch):
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", "sk-live-abcdef123456789")
    monkeypatch.setenv("INVESTIA_TEST_NOT_SECRET", "hello")
    values = env_secret_values()
    assert "sk-live-abcdef123456789" in values
    assert "hello" not in values


def test_regex_redactor_masks_env_secret(monkeypatch):
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", "sk-live-abcdef123456789")
    redactor = RegexRedactor(env_secret_values())
    out = redactor.redact("la clé est sk-live-abcdef123456789 merci")
    assert "sk-live-abcdef123456789" not in out
    assert REDACTED in out


def test_regex_redactor_masks_common_secret_and_pii_patterns():
    redactor = RegexRedactor([])
    samples = [
        "sk-abcdefghijklmnopqrst",
        "ghp_abcdefghijklmnopqrstuvwxyz",
        "AKIAIOSFODNN7EXAMPLE",
        "Bearer eyJhbGciOiJIUzI1NiJ9.payload",
        "jean.dupont@example.com",
        "tél 06 12 34 56 78",
    ]
    for sample in samples:
        out = redactor.redact(sample)
        assert sample not in out, sample
        assert REDACTED in out, sample


def test_regex_redactor_leaves_normal_text_untouched():
    redactor = RegexRedactor([])
    text = "AAPL vaut 344.63 $ selon finnhub."
    assert redactor.redact(text) == text


def test_presidio_redactor_never_crashes_and_falls_back():
    # Sans modèle spaCy téléchargé au runtime, Presidio doit se replier sur le
    # regex sans lever d'exception (aucun téléchargement réseau ici).
    redactor = PresidioRedactor(RegexRedactor([]))
    out = redactor.redact("contact: jean.dupont@example.com")
    assert "jean.dupont@example.com" not in out
    assert redactor.redact("texte normal") == "texte normal"


def test_redact_value_walks_nested_structures():
    redactor = RegexRedactor(["sk-live-abcdef123456789"])
    value = {
        "a": ["x sk-live-abcdef123456789", 1, {"b": "sk-live-abcdef123456789"}],
        "n": 2.5,
        "ok": True,
    }
    out = redact_value(value, redactor)
    assert "sk-live-abcdef123456789" not in json.dumps(out)
    assert out["n"] == 2.5
    assert out["ok"] is True


def test_default_redactor_is_chain_and_deterministic(monkeypatch):
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", "sk-live-abcdef123456789")
    redactor = default_redactor()
    assert isinstance(redactor, ChainRedactor)
    assert redactor.redact("sk-live-abcdef123456789") == REDACTED


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeSession:
    def __init__(self, captured):
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt, params=None):
        self._captured.append((str(stmt), params or {}))
        return _FakeResult(RUN_ID)

    async def commit(self):
        pass


class _FakeSessionFactory:
    def __init__(self):
        self.captured = []

    def __call__(self):
        return _FakeSession(self.captured)


async def test_log_step_redacts_secret_in_payload(monkeypatch):
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", "sk-live-abcdef123456789")
    factory = _FakeSessionFactory()
    store = DbTraceStore(factory)
    await store.log_step(
        RUN_ID, 0, "tool_call", {"result": "key=sk-live-abcdef123456789"}
    )
    payload = json.loads(factory.captured[-1][1]["payload"])
    blob = json.dumps(payload)
    assert "sk-live-abcdef123456789" not in blob
    assert REDACTED in blob


async def test_start_run_redacts_question(monkeypatch):
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", "sk-live-abcdef123456789")
    factory = _FakeSessionFactory()
    store = DbTraceStore(factory)
    await store.start_run("ma clé sk-live-abcdef123456789 ?")
    assert "sk-live-abcdef123456789" not in factory.captured[-1][1]["q"]


async def test_finish_run_redacts_answer(monkeypatch):
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", "sk-live-abcdef123456789")
    factory = _FakeSessionFactory()
    store = DbTraceStore(factory)
    await store.finish_run(
        RUN_ID,
        answer="réponse avec sk-live-abcdef123456789",
        model="gpt-6-luna",
        turns=1,
        cost_cents=0.01,
        status="ok",
    )
    assert "sk-live-abcdef123456789" not in factory.captured[-1][1]["a"]
    assert REDACTED in factory.captured[-1][1]["a"]


async def test_store_uses_injected_redactor():
    class NullRedactor:
        def redact(self, text):
            return text

    factory = _FakeSessionFactory()
    store = DbTraceStore(factory, redactor=NullRedactor())
    await store.log_step(RUN_ID, 0, "tool_call", {"result": "sk-abcdefghijklmnopqrst"})
    assert "sk-abcdefghijklmnopqrst" in factory.captured[-1][1]["payload"]
