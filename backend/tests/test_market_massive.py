"""Tests du connecteur Massive (ex-Polygon) : historique US, clôtures — HTTP mocké."""

import re

import httpx
import pytest
from pydantic import SecretStr

from investia.market.base import MarketDataError
from investia.market.massive import MassiveConnector

# 2026-10-29 et 2026-10-30, minuit UTC, en millisecondes
BARS = {
    "ticker": "AAPL",
    "status": "OK",
    "results": [
        {"t": 1793232000000, "c": 340.1},
        {"t": 1793318400000, "c": 344.63},
        {"t": 1793404800000, "c": 345.5},
    ],
}


def make_connector(handler) -> MassiveConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MassiveConnector(api_key=SecretStr("ms-test"), client=client)


async def test_get_history_returns_daily_closes_oldest_first():
    def handler(request: httpx.Request) -> httpx.Response:
        match = re.fullmatch(
            r"/v2/aggs/ticker/AAPL/range/1/day/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})",
            request.url.path,
        )
        assert match, request.url.path
        assert match.group(1) < match.group(2)
        assert request.url.params["adjusted"] == "true"
        assert request.url.params["sort"] == "asc"
        return httpx.Response(200, json=BARS)

    history = await make_connector(handler).get_history("AAPL", days=30)
    assert [h.value for h in history] == [340.1, 344.63, 345.5]
    assert history[0].timestamp.isoformat() == "2026-10-29T00:00:00+00:00"
    assert all(h.currency == "USD" for h in history)
    assert all(h.source == "massive" for h in history)
    assert all(h.delayed for h in history)


async def test_keeps_only_the_requested_number_of_days():
    connector = make_connector(lambda request: httpx.Response(200, json=BARS))
    history = await connector.get_history("AAPL", days=2)
    assert [h.value for h in history] == [344.63, 345.5]


async def test_api_key_goes_in_the_header_never_in_the_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer ms-test"
        assert "apiKey" not in request.url.params
        assert "ms-test" not in str(request.url)
        return httpx.Response(200, json=BARS)

    await make_connector(handler).get_history("AAPL", days=30)


async def test_http_429_is_flagged_rate_limited():
    connector = make_connector(lambda request: httpx.Response(429))
    with pytest.raises(MarketDataError) as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is True


async def test_http_error_names_the_source():
    connector = make_connector(lambda request: httpx.Response(401))
    with pytest.raises(MarketDataError, match="massive: HTTP 401 pour AAPL") as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is False


async def test_no_results_is_an_error_so_the_cascade_moves_on():
    payload = {"ticker": "ZZZZ", "status": "OK", "resultsCount": 0}
    connector = make_connector(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(MarketDataError, match="aucune donnée"):
        await connector.get_history("ZZZZ", days=30)


async def test_quote_and_news_are_not_supported():
    connector = make_connector(lambda request: httpx.Response(200, json=BARS))
    with pytest.raises(MarketDataError, match="non supporté"):
        await connector.get_quote("AAPL")
    with pytest.raises(MarketDataError, match="non supporté"):
        await connector.get_news("AAPL")
