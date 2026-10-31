"""Tests d'intégration du TraceStore contre une vraie base PostgreSQL."""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from investia.db import get_session
from investia.tracing import DbTraceStore

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(monkeypatch):
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    import investia.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    yield DbTraceStore(get_session())
    db_module._engine = None
    db_module._session_factory = None


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
def test_alembic_upgrade_head_creates_runs_tables():
    assert TEST_DATABASE_URL is not None
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
async def test_trace_store_roundtrip_on_real_db(store):
    run_id = await store.start_run("prix AAPL ?")
    await store.log_step(
        run_id, 1, "llm_call", {"model": "gpt-6-luna", "cost_cents": 0.01}
    )
    await store.log_step(run_id, 1, "tool_call", {"name": "get_quote", "ok": True})
    await store.log_step(run_id, 2, "guardrail", {"check": "numbers", "ok": True})
    await store.finish_run(
        run_id,
        answer="réponse",
        model="gpt-6-luna",
        turns=2,
        cost_cents=0.02,
        status="ok",
    )
    data = await store.get_run(run_id)
    assert data["run"]["status"] == "ok"
    assert data["run"]["question"] == "prix AAPL ?"
    assert [s["kind"] for s in data["steps"]] == ["llm_call", "tool_call", "guardrail"]
    assert data["steps"][1]["payload"]["name"] == "get_quote"


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
async def test_run_steps_table_exists_after_migration(store):
    async with get_session()() as session:
        count = await session.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name='run_steps'"
            )
        )
        assert count.scalar() == 1
