"""Tests de la connexion Redis async et de la route /ready (partie cache)."""

import os

import httpx
import pytest

from investia.cache import check_redis, get_redis
from investia.main import create_app

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL")
HAS_TEST_DB = bool(os.environ.get("TEST_DATABASE_URL"))

BASE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@127.0.0.1:59999/nope",
    "LITELLM_BASE_URL": "http://localhost:4000",
    "LITELLM_MASTER_KEY": "sk-test",
    "APP_SECRET_KEY": "test-admin-secret-0123456789abcdef",
}


@pytest.fixture
def reset_globals():
    import investia.cache as cache_module
    import investia.db as db_module

    cache_module._redis = None
    db_module._engine = None
    db_module._session_factory = None
    yield
    cache_module._redis = None
    db_module._engine = None
    db_module._session_factory = None


@pytest.mark.integration
@pytest.mark.skipif(not TEST_REDIS_URL, reason="TEST_REDIS_URL non défini")
async def test_check_redis_true_with_real_redis(monkeypatch, reset_globals):
    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    assert await check_redis() is True
    redis = get_redis()
    assert await redis.ping() is True


async def test_ready_reports_redis_down_without_exception_text(
    monkeypatch, reset_globals
):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59998/0")
    for var, value in BASE_ENV.items():
        monkeypatch.setenv(var, value)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ready = await client.get("/ready")
    assert ready.status_code == 503
    assert ready.json() == {"db": "down", "redis": "down"}
    assert "redis" not in ready.text.lower().replace('"redis"', "")
    assert "ConnectionError" not in ready.text


@pytest.mark.integration
@pytest.mark.skipif(not TEST_REDIS_URL, reason="TEST_REDIS_URL non défini")
@pytest.mark.skipif(not HAS_TEST_DB, reason="TEST_DATABASE_URL non défini")
async def test_ready_200_when_db_and_redis_up(monkeypatch, reset_globals):
    assert TEST_REDIS_URL is not None
    test_db_url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    for var, value in BASE_ENV.items():
        if var != "DATABASE_URL":
            monkeypatch.setenv(var, value)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"db": "up", "redis": "up"}
