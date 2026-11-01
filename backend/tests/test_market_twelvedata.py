"""Tests du connecteur Twelve Data (historique US, clôtures) — HTTP mocké."""

import httpx
import pytest
from pydantic import SecretStr

from investia.market.base import MarketDataError
from investia.market.twelvedata import TwelveDataConnector

SERIES = {
    "meta": {
        "symbol": "AAPL",
        "interval": "1day",
        "currency": "USD",
        "type": "Common Stock",
    },
    # Twelve Data renvoie les jours les plus récents d'abord.
    "values": [
        {"datetime": "2026-10-30", "close": "344.63000"},
        {"datetime": "2026-10-29", "close": "340.10000"},
    ],
    "status": "ok",
}


def make_connector(handler) -> TwelveDataConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TwelveDataConnector(api_key=SecretStr("td-test"), client=client)


async def test_get_history_returns_closes_oldest_first_with_currency():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/time_series"
        assert request.url.params["symbol"] == "AAPL"
        assert request.url.params["interval"] == "1day"
        assert request.url.params["outputsize"] == "30"
        return httpx.Response(200, json=SERIES)

    history = await make_connector(handler).get_history("AAPL", days=30)
    assert [h.value for h in history] == [340.1, 344.63]
    assert [h.timestamp.date().isoformat() for h in history] == [
        "2026-10-29",
        "2026-10-30",
    ]
    assert all(h.currency == "USD" for h in history)
    assert all(h.source == "twelvedata" for h in history)
    assert all(h.delayed for h in history)


async def test_api_key_goes_in_the_header_never_in_the_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "apikey td-test"
        assert "apikey" not in request.url.params
        assert "td-test" not in str(request.url)
        return httpx.Response(200, json=SERIES)

    await make_connector(handler).get_history("AAPL", days=30)


async def test_error_payload_raises_with_the_provider_message():
    payload = {"code": 400, "message": "symbol not found", "status": "error"}
    connector = make_connector(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(
        MarketDataError, match="twelvedata: .*symbol not found"
    ) as caught:
        await connector.get_history("ZZZZ", days=30)
    assert caught.value.rate_limited is False


async def test_quota_error_payload_is_flagged_rate_limited():
    payload = {"code": 429, "message": "run out of API credits", "status": "error"}
    connector = make_connector(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(MarketDataError) as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is True


async def test_http_429_is_flagged_rate_limited():
    connector = make_connector(lambda request: httpx.Response(429))
    with pytest.raises(MarketDataError) as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is True


async def test_http_error_names_the_source():
    connector = make_connector(lambda request: httpx.Response(500))
    with pytest.raises(MarketDataError, match="twelvedata: HTTP 500 pour AAPL"):
        await connector.get_history("AAPL", days=30)


async def test_response_without_values_is_a_clear_error():
    payload = {"meta": SERIES["meta"], "status": "ok"}
    connector = make_connector(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(MarketDataError, match="réponse inattendue"):
        await connector.get_history("AAPL", days=30)


async def test_empty_values_is_an_error_so_the_cascade_moves_on():
    payload = {"meta": SERIES["meta"], "values": [], "status": "ok"}
    connector = make_connector(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(MarketDataError, match="aucune donnée"):
        await connector.get_history("AAPL", days=30)


async def test_quote_and_news_are_not_supported():
    connector = make_connector(lambda request: httpx.Response(200, json=SERIES))
    with pytest.raises(MarketDataError, match="non supporté"):
        await connector.get_quote("AAPL")
    with pytest.raises(MarketDataError, match="non supporté"):
        await connector.get_news("AAPL")
