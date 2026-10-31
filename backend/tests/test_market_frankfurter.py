"""Tests du connecteur Frankfurter/ECB (taux de change) — HTTP mocké, sans clé."""

import httpx
import pytest

from investia.market.base import MarketDataError
from investia.market.frankfurter import FrankfurterConnector


def make_connector(handler) -> FrankfurterConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FrankfurterConnector(client=client)


async def test_get_quote_fx_returns_rate():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["from"] == "USD"
        assert request.url.params["to"] == "EUR"
        return httpx.Response(
            200,
            json={
                "amount": 1.0,
                "base": "USD",
                "date": "2026-10-30",
                "rates": {"EUR": 0.89509},
            },
        )

    connector = make_connector(handler)
    data = await connector.get_quote("USD")
    assert data.value == 0.89509
    assert data.currency == "EUR"
    assert data.source == "frankfurter"


async def test_get_history_fx_returns_daily_rates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "base": "USD",
                "rates": {"2026-10-28": {"EUR": 0.895}, "2026-10-29": {"EUR": 0.896}},
            },
        )

    connector = make_connector(handler)
    history = await connector.get_history("USD", days=30)
    assert [h.value for h in history] == [0.895, 0.896]


async def test_fx_error_raises_and_names_source():
    connector = make_connector(lambda request: httpx.Response(404))
    with pytest.raises(MarketDataError, match="frankfurter"):
        await connector.get_quote("XXX")
