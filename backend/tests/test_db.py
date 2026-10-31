"""Tests de la connexion PostgreSQL async, d'Alembic et de la route /ready."""

import os
import subprocess
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from investia.db import check_db, get_session
from investia.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

BASE_ENV = {
    "REDIS_URL": "redis://localhost:6379/0",
    "LITELLM_BASE_URL": "http://localhost:4000",
    "LITELLM_MASTER_KEY": "sk-test",
    "APP_SECRET_KEY": "test-secret",
}


@pytest.fixture
def reset_db_globals():
    import investia.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    yield
    db_module._engine = None
    db_module._session_factory = None


@pytest.mark.integration
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
async def test_check_db_true_and_select_1_with_real_postgres(
    monkeypatch, reset_db_globals
):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    assert await check_db() is True
    async with get_session()() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_app_starts_and_ready_503_when_db_down(monkeypatch, reset_db_globals):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:59999/nope")
    for var, value in BASE_ENV.items():
        monkeypatch.setenv(var, value)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        ready = await client.get("/ready")
    assert health.status_code == 200
    assert ready.status_code == 503
    assert ready.json() == {"db": "down"}
    assert "asyncpg" not in ready.text
    assert "OperationalError" not in ready.text


@pytest.mark.integration
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
async def test_ready_200_when_db_up(monkeypatch, reset_db_globals):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    for var, value in BASE_ENV.items():
        monkeypatch.setenv(var, value)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"db": "up"}


@pytest.mark.integration
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
def test_alembic_upgrade_head_on_empty_db():
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
