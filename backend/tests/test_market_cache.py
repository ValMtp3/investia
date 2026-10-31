"""Tests du cache Redis TTL générique."""

import os

import pytest

from investia.market.cache import cached

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL")


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex


@pytest.fixture
def fake_redis(monkeypatch):
    import investia.market.cache as cache_module

    fake = FakeRedis()
    monkeypatch.setattr(cache_module, "get_redis", lambda: fake)
    return fake


async def test_cached_calls_factory_once_and_stores_with_ttl(fake_redis):
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return {"value": 42}

    first = await cached("quote:AAPL", ttl=60, factory=factory)
    second = await cached("quote:AAPL", ttl=60, factory=factory)
    assert first == second == {"value": 42}
    assert calls == 1
    assert fake_redis.ttls["quote:AAPL"] == 60


@pytest.mark.integration
@pytest.mark.skipif(not TEST_REDIS_URL, reason="TEST_REDIS_URL non défini")
async def test_cached_with_real_redis(monkeypatch):
    import investia.cache as redis_module

    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    redis_module._redis = None
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return {"price": 100.0}

    key = "test:cached:real"
    await redis_module.get_redis().delete(key)
    first = await cached(key, ttl=60, factory=factory)
    second = await cached(key, ttl=60, factory=factory)
    assert first == second == {"price": 100.0}
    assert calls == 1
    await redis_module.get_redis().delete(key)
    redis_module._redis = None
