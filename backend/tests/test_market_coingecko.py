"""Tests du connecteur CoinGecko (crypto) — HTTP mocké."""

import httpx
import pytest
from pydantic import SecretStr

from investia.market.base import MarketDataError
from investia.market.coingecko import CoinGeckoConnector


def make_connector(handler) -> CoinGeckoConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CoinGeckoConnector(api_key=SecretStr("cg-test"), client=client)


async def test_get_quote_crypto_returns_eur():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "bitcoin" in str(request.url)
        assert request.url.params["vs_currencies"] == "eur"
        return httpx.Response(200, json={"bitcoin": {"eur": 69245.0}})

    connector = make_connector(handler)
    data = await connector.get_quote("BTC-USD")
    assert data.value == 69245.0
    assert data.currency == "EUR"
    assert data.source == "coingecko"


async def test_get_history_returns_price_points():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/market_chart")
        return httpx.Response(
            200, json={"prices": [[1793300000000, 68000.0], [1793386400000, 69245.0]]}
        )

    connector = make_connector(handler)
    history = await connector.get_history("BTC-USD", days=2)
    assert [h.value for h in history] == [68000.0, 69245.0]


async def test_http_error_raises_and_names_source():
    connector = make_connector(lambda request: httpx.Response(429))
    with pytest.raises(MarketDataError, match="coingecko"):
        await connector.get_quote("BTC-USD")
