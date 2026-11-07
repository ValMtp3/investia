"""Cascade de sources (spec 4.4d) : plan B, plan C, pause après 429, cache 24 h."""

from datetime import UTC, datetime

import pytest

from investia.market.base import MarketData, MarketDataError
from investia.market.service import TTL_HISTORY, MarketService


def point(source: str, value: float = 100.0) -> MarketData:
    return MarketData(
        value=value,
        currency="USD",
        source=source,
        timestamp=datetime(2026, 10, 30, tzinfo=UTC),
        delayed=True,
    )


class Scripted:
    """Faux connecteur : renvoie un historique, ou lève l'erreur donnée."""

    def __init__(self, name: str, error: MarketDataError | None = None):
        self.name = name
        self._error = error
        self.calls = 0

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        self.calls += 1
        if self._error:
            raise self._error
        return [point(self.name)]

    async def get_quote(self, symbol: str) -> MarketData:
        raise NotImplementedError

    async def get_news(self, symbol: str, limit: int = 5):
        return []


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

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


def failing(name: str, detail: str = "HTTP 500", rate_limited: bool = False):
    return Scripted(name, MarketDataError(name, detail, rate_limited=rate_limited))


async def test_first_source_answers_and_the_others_are_not_called(fake_redis):
    yahoo, eodhd = Scripted("yahoo"), Scripted("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "yahoo"
    assert (yahoo.calls, eodhd.calls) == (1, 0)


async def test_falls_back_to_the_next_source_when_the_first_fails(fake_redis):
    yahoo, eodhd = failing("yahoo", "HTTP 500 pour AAPL"), Scripted("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "eodhd"
    assert (yahoo.calls, eodhd.calls) == (1, 1)


async def test_goes_down_the_whole_chain_to_the_last_source(fake_redis):
    connectors = {
        "yahoo": failing("yahoo"),
        "eodhd": failing("eodhd", "HTTP 404"),
        "twelvedata": failing("twelvedata", "quota"),
        "massive": Scripted("massive"),
    }
    service = MarketService(connectors=connectors)
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "massive"


async def test_all_sources_failing_lists_every_attempt(fake_redis):
    service = MarketService(
        connectors={
            "yahoo": failing("yahoo", "HTTP 500 pour AAPL"),
            "eodhd": failing("eodhd", "HTTP 404 pour AAPL.US"),
        }
    )
    with pytest.raises(MarketDataError) as caught:
        await service.get_history("AAPL", days=30)
    message = str(caught.value)
    assert "AAPL" in message
    assert "yahoo: HTTP 500 pour AAPL" in message
    assert "eodhd: HTTP 404 pour AAPL.US" in message
    assert "twelvedata: non configuré" in message
    assert "massive: non configuré" in message


async def test_unconfigured_sources_are_skipped(fake_redis):
    eodhd = Scripted("eodhd")
    service = MarketService(connectors={"eodhd": eodhd})
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "eodhd"


async def test_europe_history_uses_eodhd_only(fake_redis):
    yahoo, eodhd = Scripted("yahoo"), Scripted("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})
    history = await service.get_history("SAP.DE", days=30)
    assert history[0].source == "eodhd"
    assert yahoo.calls == 0


async def test_rate_limited_source_is_paused_for_10_minutes(fake_redis):
    yahoo = failing("yahoo", "HTTP 429 pour AAPL", rate_limited=True)
    eodhd = Scripted("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})

    await service.get_history("AAPL", days=30)
    assert fake_redis.ttls["cooldown:yahoo"] == 600

    # Autre symbole (pas de cache) : Yahoo est en pause, il n'est plus appelé.
    await service.get_history("MSFT", days=30)
    assert yahoo.calls == 1
    assert eodhd.calls == 2


async def test_pause_is_mentioned_when_every_source_fails(fake_redis):
    yahoo = failing("yahoo", "HTTP 429 pour AAPL", rate_limited=True)
    service = MarketService(connectors={"yahoo": yahoo})
    with pytest.raises(
        MarketDataError, match=r"yahoo: HTTP 429 pour AAPL \(en pause\)"
    ):
        await service.get_history("AAPL", days=30)
    with pytest.raises(MarketDataError, match=r"yahoo: en pause"):
        await service.get_history("MSFT", days=30)


async def test_ordinary_failure_does_not_pause_the_source(fake_redis):
    yahoo, eodhd = failing("yahoo", "HTTP 500"), Scripted("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})
    await service.get_history("AAPL", days=30)
    assert "cooldown:yahoo" not in fake_redis.store


async def test_history_is_cached_for_24_hours(fake_redis):
    assert TTL_HISTORY == 86_400
    yahoo = Scripted("yahoo")
    service = MarketService(connectors={"yahoo": yahoo})
    await service.get_history("AAPL", days=30)
    await service.get_history("AAPL", days=30)
    assert yahoo.calls == 1
    assert fake_redis.ttls["history:AAPL:30"] == 86_400


async def test_failures_are_never_cached(fake_redis):
    service = MarketService(connectors={"yahoo": failing("yahoo")})
    with pytest.raises(MarketDataError):
        await service.get_history("AAPL", days=30)
    assert "history:AAPL:30" not in fake_redis.store


async def test_without_cache_there_is_no_redis_and_no_pause(fake_redis):
    yahoo = failing("yahoo", "HTTP 429", rate_limited=True)
    eodhd = Scripted("eodhd")
    service = MarketService(
        connectors={"yahoo": yahoo, "eodhd": eodhd}, use_cache=False
    )
    await service.get_history("AAPL", days=30)
    await service.get_history("AAPL", days=30)
    assert fake_redis.store == {}
    assert yahoo.calls == 2
