"""Tests du connecteur EODHD (historique EOD Europe) — HTTP mocké."""

import httpx
import pytest
from pydantic import SecretStr

from investia.market.base import MarketDataError
from investia.market.eodhd import EodhdConnector


def make_connector(handler) -> EodhdConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return EodhdConnector(api_key=SecretStr("eodhd-test"), client=client)


async def test_get_history_maps_de_suffix_to_xetra():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/eod/SAP.XETRA"
        assert request.url.params["api_token"] == "eodhd-test"
        return httpx.Response(
            200,
            json=[
                {"date": "2026-10-29", "close": 188.0},
                {"date": "2026-10-30", "close": 189.4},
            ],
        )

    connector = make_connector(handler)
    history = await connector.get_history("SAP.DE", days=30)
    assert [h.value for h in history] == [188.0, 189.4]
    assert all(h.source == "eodhd" for h in history)
    assert all(h.currency == "EUR" for h in history)


async def test_get_history_pa_suffix_stays_pa():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/eod/AIR.PA"
        return httpx.Response(200, json=[{"date": "2026-10-30", "close": 175.2}])

    connector = make_connector(handler)
    history = await connector.get_history("AIR.PA", days=10)
    assert history[0].value == 175.2


async def test_get_quote_not_available_on_free_tier():
    connector = make_connector(lambda request: httpx.Response(200, json=[]))
    with pytest.raises(MarketDataError, match="payant"):
        await connector.get_quote("SAP.DE")


async def test_http_error_raises_and_names_source():
    connector = make_connector(lambda request: httpx.Response(401))
    with pytest.raises(MarketDataError, match="eodhd"):
        await connector.get_history("SAP.DE")


async def test_get_history_us_symbol_uses_the_us_exchange_and_usd():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/eod/AAPL.US"
        return httpx.Response(
            200,
            json=[
                {"date": "2026-10-29", "close": 340.1},
                {"date": "2026-10-30", "close": 344.63},
            ],
        )

    history = await make_connector(handler).get_history("AAPL", days=30)
    assert [h.value for h in history] == [340.1, 344.63]
    assert all(h.currency == "USD" for h in history)
    assert all(h.source == "eodhd" for h in history)


async def test_429_is_flagged_rate_limited():
    connector = make_connector(lambda request: httpx.Response(429))
    with pytest.raises(MarketDataError) as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is True
