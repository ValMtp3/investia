"""Durcissement (revue 4.4c/4.4d) : erreurs réseau, vide, Redis, pause, flux."""

import logging
from datetime import UTC, datetime

import httpx
import pytest

from investia.main import create_app
from investia.market.base import MarketData, MarketDataError
from investia.market.service import PAUSE_SECONDS, TTL_FAILURE, MarketService


def point(source: str, value: float = 100.0) -> MarketData:
    return MarketData(
        value=value,
        currency="USD",
        source=source,
        timestamp=datetime(2026, 10, 30, tzinfo=UTC),
        delayed=True,
    )


class Connector:
    """Faux connecteur : historique donné, ou erreur donnée (historique et prix)."""

    def __init__(self, name, history=None, error=None, quote_error=None):
        self.name = name
        self._history = [point(name)] if history is None else history
        self._error = error
        self._quote_error = quote_error
        self.history_calls = 0
        self.quote_calls = 0

    async def get_history(self, symbol, days=30):
        self.history_calls += 1
        if self._error:
            raise self._error
        return self._history

    async def get_quote(self, symbol):
        self.quote_calls += 1
        if self._quote_error:
            raise self._quote_error
        return point(self.name)

    async def get_news(self, symbol, limit=5):
        return []


class FakeRedis:
    def __init__(self, broken=False):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.broken = broken

    async def get(self, key):
        if self.broken:
            raise ConnectionError("Redis est tombé")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if self.broken:
            raise ConnectionError("Redis est tombé")
        self.store[key] = value
        self.ttls[key] = ex


@pytest.fixture
def fake_redis(monkeypatch):
    import investia.market.cache as cache_module

    fake = FakeRedis()
    monkeypatch.setattr(cache_module, "get_redis", lambda: fake)
    return fake


@pytest.fixture
def broken_redis(monkeypatch):
    import investia.market.cache as cache_module

    fake = FakeRedis(broken=True)
    monkeypatch.setattr(cache_module, "get_redis", lambda: fake)
    return fake


# --- La cascade ne s'arrête pas sur une erreur autre que MarketDataError ---


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectTimeout("trop lent"),
        httpx.ConnectError("réseau coupé"),
        KeyError("indicators"),
        ValueError("JSON invalide"),
        TypeError("None n'est pas indexable"),
    ],
    ids=["timeout", "connexion", "champ absent", "valeur", "type"],
)
async def test_unexpected_error_in_a_source_does_not_break_the_chain(fake_redis, error):
    yahoo, eodhd = Connector("yahoo", error=error), Connector("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "eodhd"
    assert yahoo.history_calls == 1


async def test_unexpected_errors_are_listed_by_type_in_the_final_error(fake_redis):
    service = MarketService(
        connectors={
            "yahoo": Connector("yahoo", error=httpx.ConnectTimeout("lent")),
            "eodhd": Connector("eodhd", error=KeyError("close")),
        }
    )
    with pytest.raises(MarketDataError) as caught:
        await service.get_history("AAPL", days=30)
    message = str(caught.value)
    assert "yahoo: erreur réseau ou format (ConnectTimeout)" in message
    assert "eodhd: erreur réseau ou format (KeyError)" in message


# --- Un historique vide est un échec, pas un succès à mettre en cache ---


async def test_empty_history_moves_on_to_the_next_source(fake_redis):
    yahoo = Connector("yahoo", history=[])
    eodhd = Connector("eodhd")
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": eodhd})
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "eodhd"


async def test_all_empty_is_an_error_and_nothing_is_cached(fake_redis):
    service = MarketService(
        connectors={
            "yahoo": Connector("yahoo", history=[]),
            "eodhd": Connector("eodhd", history=[]),
        }
    )
    with pytest.raises(MarketDataError, match="yahoo: aucune donnée"):
        await service.get_history("AAPL", days=30)
    assert "history:AAPL:30" not in fake_redis.store


# --- Un échec total est retenu quelques minutes (ménage les quotas) ---


async def test_total_failure_is_remembered_for_5_minutes(fake_redis):
    assert TTL_FAILURE == 300
    yahoo = Connector("yahoo", error=MarketDataError("yahoo", "HTTP 500 pour AAPL"))
    service = MarketService(connectors={"yahoo": yahoo})

    with pytest.raises(MarketDataError) as first:
        await service.get_history("AAPL", days=30)
    assert fake_redis.ttls["history-failed:AAPL:30"] == TTL_FAILURE

    with pytest.raises(MarketDataError) as second:
        await service.get_history("AAPL", days=30)
    assert str(second.value) == str(first.value)
    assert yahoo.history_calls == 1, "le 2e appel ne doit pas relancer la cascade"


async def test_failure_memory_is_per_symbol(fake_redis):
    yahoo = Connector("yahoo", error=MarketDataError("yahoo", "HTTP 500"))
    service = MarketService(connectors={"yahoo": yahoo})
    for symbol in ("AAPL", "MSFT"):
        with pytest.raises(MarketDataError):
            await service.get_history(symbol, days=30)
    assert yahoo.history_calls == 2


async def test_no_failure_memory_without_cache(fake_redis):
    yahoo = Connector("yahoo", error=MarketDataError("yahoo", "HTTP 500"))
    service = MarketService(connectors={"yahoo": yahoo}, use_cache=False)
    for _ in range(2):
        with pytest.raises(MarketDataError):
            await service.get_history("AAPL", days=30)
    assert yahoo.history_calls == 2
    assert fake_redis.store == {}


# --- Redis en panne : une optimisation perdue, pas un service coupé ---


async def test_history_still_works_when_redis_is_down(broken_redis):
    yahoo = Connector("yahoo")
    service = MarketService(connectors={"yahoo": yahoo})
    history = await service.get_history("AAPL", days=30)
    assert history[0].source == "yahoo"


async def test_quote_still_works_when_redis_is_down(broken_redis):
    finnhub = Connector("finnhub")
    service = MarketService(connectors={"finnhub": finnhub})
    quote = await service.get_quote("AAPL")
    assert quote.source == "finnhub"


async def test_failures_are_still_reported_when_redis_is_down(broken_redis):
    service = MarketService(
        connectors={
            "yahoo": Connector("yahoo", error=MarketDataError("yahoo", "HTTP 500"))
        }
    )
    with pytest.raises(MarketDataError, match="yahoo: HTTP 500"):
        await service.get_history("AAPL", days=30)


# --- La pause après un 429 protège aussi le prix en direct ---


async def test_rate_limited_quote_pauses_the_source(fake_redis):
    yahoo = Connector(
        "yahoo",
        quote_error=MarketDataError("yahoo", "HTTP 429 pour SAP.DE", rate_limited=True),
    )
    service = MarketService(connectors={"yahoo": yahoo})
    with pytest.raises(MarketDataError, match="HTTP 429"):
        await service.get_quote("SAP.DE")
    assert fake_redis.ttls["cooldown:yahoo"] == PAUSE_SECONDS

    # Autre symbole (pas de cache) : Yahoo est en pause, il n'est pas rappelé.
    with pytest.raises(MarketDataError, match="yahoo: en pause"):
        await service.get_quote("AIR.PA")
    assert yahoo.quote_calls == 1


async def test_ordinary_quote_failure_does_not_pause(fake_redis):
    yahoo = Connector(
        "yahoo", quote_error=MarketDataError("yahoo", "HTTP 500 pour SAP.DE")
    )
    service = MarketService(connectors={"yahoo": yahoo})
    with pytest.raises(MarketDataError):
        await service.get_quote("SAP.DE")
    assert "cooldown:yahoo" not in fake_redis.store


async def test_pause_set_by_the_history_also_protects_the_quote(fake_redis):
    yahoo = Connector(
        "yahoo",
        error=MarketDataError("yahoo", "HTTP 429 pour AAPL", rate_limited=True),
    )
    service = MarketService(connectors={"yahoo": yahoo, "eodhd": Connector("eodhd")})
    await service.get_history("AAPL", days=30)  # Yahoo 429 -> pause, EODHD répond
    with pytest.raises(MarketDataError, match="yahoo: en pause"):
        await service.get_quote("SAP.DE")
    assert yahoo.quote_calls == 0


# --- /market/stream : entrées validées, débit borné ---


class StreamMarket:
    def __init__(self):
        self.quote_calls: list[str] = []

    async def get_quote(self, symbol):
        self.quote_calls.append(symbol)
        return point("finnhub")

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


class FakePortfolio:
    async def get_portfolio(self):
        return {}


@pytest.fixture
def stream_app(monkeypatch):
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "APP_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "x")
    market = StreamMarket()
    app = create_app(portfolio_service=FakePortfolio(), llm=object(), market=market)
    return app, market


async def stream_status(app, **params) -> int:
    """Code HTTP du flux. Paramètres encodés (un `#` ou un `?` ne doit pas couper l'URL)
    et `max_events=1` par défaut : un test ne doit jamais ouvrir un flux sans fin."""
    params.setdefault("max_events", 1)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/market/stream", params=params) as response:
            async for _ in response.aiter_text():
                pass
            return response.status_code


@pytest.mark.parametrize(
    "symbols",
    ["../etc", "AA/PL", "AA PL", "AAPL?x=1", "AAPL#", "A" * 21, "AAPL,,../x", ""],
)
async def test_stream_rejects_invalid_symbols(stream_app, symbols):
    app, market = stream_app
    status = await stream_status(app, symbols=symbols)
    assert status == 422
    assert market.quote_calls == []


async def test_stream_rejects_too_many_symbols(stream_app):
    app, market = stream_app
    many = ",".join(f"SYM{i}" for i in range(21))
    assert await stream_status(app, symbols=many) == 422
    assert market.quote_calls == []


async def test_stream_accepts_up_to_20_symbols(stream_app):
    app, market = stream_app
    twenty = ",".join(f"SYM{i}" for i in range(20))
    assert await stream_status(app, symbols=twenty) == 200
    assert len(market.quote_calls) == 20


@pytest.mark.parametrize("interval", ["0", "0.5", "-1"])
async def test_stream_rejects_an_interval_under_one_second(stream_app, interval):
    app, market = stream_app
    status = await stream_status(app, symbols="AAPL", interval=interval)
    assert status == 422
    assert market.quote_calls == []


async def test_stream_valid_symbols_are_streamed(stream_app):
    app, market = stream_app
    assert await stream_status(app, symbols="aapl,SAP.DE,BTC-USD") == 200
    assert market.quote_calls == ["AAPL", "SAP.DE", "BTC-USD"]


# --- Les clés dans l'URL ne finissent pas dans les logs ---


def test_httpx_does_not_log_request_urls(stream_app):
    # httpx écrit l'URL complète (donc `api_token=...`) au niveau INFO.
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
