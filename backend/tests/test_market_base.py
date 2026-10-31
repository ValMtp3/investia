"""Tests du format commun MarketData et de l'erreur fournisseur."""

from datetime import UTC, datetime

from investia.market.base import MarketData, MarketDataError


def test_market_data_has_all_common_fields():
    data = MarketData(
        value=344.63,
        currency="USD",
        source="finnhub",
        timestamp=datetime(2026, 10, 31, 15, 0, tzinfo=UTC),
    )
    assert data.value == 344.63
    assert data.currency == "USD"
    assert data.source == "finnhub"
    assert data.delayed is False


def test_market_data_dict_roundtrip():
    data = MarketData(
        value=189.4,
        currency="EUR",
        source="yahoo",
        timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        delayed=True,
    )
    restored = MarketData.from_dict(data.to_dict())
    assert restored == data


def test_market_data_error_names_the_source():
    err = MarketDataError("finnhub", "HTTP 500")
    assert "finnhub" in str(err)
    assert err.source == "finnhub"
