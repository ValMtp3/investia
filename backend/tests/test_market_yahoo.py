"""Tests du connecteur Yahoo Finance (Europe) — HTTP mocké."""

import httpx
import pytest

from investia.market.base import MarketDataError
from investia.market.yahoo import YahooConnector


def make_connector(handler) -> YahooConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return YahooConnector(client=client, retry_delay=0)


def chart_payload(closes, currency="EUR", market_time=1793390400):
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": currency,
                        "regularMarketPrice": closes[-1],
                        "regularMarketTime": market_time,
                    },
                    "timestamp": [1793300000 + i * 86400 for i in range(len(closes))],
                    "indicators": {"quote": [{"close": closes}]},
                }
            ],
            "error": None,
        }
    }


async def test_get_quote_europe_returns_eur_delayed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/SAP.DE")
        return httpx.Response(200, json=chart_payload([188.0, 189.4]))

    connector = make_connector(handler)
    data = await connector.get_quote("SAP.DE")
    assert data.value == 189.4
    assert data.currency == "EUR"
    assert data.source == "yahoo"
    assert data.delayed is True


async def test_get_history_returns_one_point_per_day():
    connector = make_connector(
        lambda request: httpx.Response(200, json=chart_payload([10.0, None, 12.0]))
    )
    history = await connector.get_history("VWCE.DE", days=3)
    assert [h.value for h in history] == [10.0, 12.0]
    assert all(h.source == "yahoo" for h in history)


async def test_unknown_symbol_raises_and_names_source():
    payload = {"chart": {"result": [], "error": None}}
    connector = make_connector(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(MarketDataError, match="yahoo"):
        await connector.get_quote("NOPE.DE")


async def test_http_error_raises():
    connector = make_connector(lambda request: httpx.Response(429))
    with pytest.raises(MarketDataError, match="HTTP 429"):
        await connector.get_quote("SAP.DE")


async def test_news_not_available():
    connector = make_connector(
        lambda request: httpx.Response(200, json=chart_payload([1.0]))
    )
    with pytest.raises(MarketDataError, match="news"):
        await connector.get_news("SAP.DE")


async def test_429_is_flagged_rate_limited():
    connector = make_connector(lambda request: httpx.Response(429))
    with pytest.raises(MarketDataError) as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is True


async def test_other_http_errors_are_not_rate_limited():
    connector = make_connector(lambda request: httpx.Response(500))
    with pytest.raises(MarketDataError) as caught:
        await connector.get_history("AAPL", days=30)
    assert caught.value.rate_limited is False
