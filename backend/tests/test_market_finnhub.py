"""Tests du connecteur Finnhub — HTTP mocké via httpx.MockTransport."""

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from investia.market.base import MarketDataError
from investia.market.finnhub import FinnhubConnector


def make_connector(handler) -> FinnhubConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FinnhubConnector(api_key=SecretStr("sk-test"), client=client)


async def test_get_quote_returns_market_data_with_source_and_timestamp():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        assert request.url.params["token"] == "sk-test"
        return httpx.Response(200, json={"c": 344.63, "t": 1793390400})

    connector = make_connector(handler)
    data = await connector.get_quote("AAPL")
    assert data.value == 344.63
    assert data.source == "finnhub"
    assert data.currency == "USD"
    assert data.timestamp == datetime.fromtimestamp(1793390400, tz=UTC)
    assert data.delayed is False


async def test_get_quote_api_error_raises_and_names_source():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"error": "You don't have access to this resource."}
        )

    connector = make_connector(handler)
    with pytest.raises(MarketDataError, match="finnhub"):
        await connector.get_quote("SAP.DE")


async def test_get_quote_http_500_raises():
    connector = make_connector(lambda request: httpx.Response(500))
    with pytest.raises(MarketDataError, match="HTTP 500"):
        await connector.get_quote("AAPL")


async def test_get_history_is_not_available_on_free_tier():
    connector = make_connector(lambda request: httpx.Response(200, json={}))
    with pytest.raises(MarketDataError, match="payant"):
        await connector.get_history("AAPL")


async def test_get_news_returns_limited_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/company-news"
        return httpx.Response(200, json=[{"headline": f"news {i}"} for i in range(10)])

    connector = make_connector(handler)
    news = await connector.get_news("AAPL", limit=3)
    assert len(news) == 3
    assert news[0]["headline"] == "news 0"
