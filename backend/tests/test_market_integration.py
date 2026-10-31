"""Tests d'intégration réels des connecteurs (réseau + vraies clés + vrai Redis)."""

import os

import pytest

from investia.config import Settings
from investia.market import build_market_service

pytestmark = pytest.mark.integration

HAS_FINNHUB = bool(os.environ.get("FINNHUB_API_KEY"))
HAS_REDIS = bool(os.environ.get("TEST_REDIS_URL"))


@pytest.mark.skipif(not HAS_FINNHUB, reason="FINNHUB_API_KEY manquante")
@pytest.mark.skipif(not HAS_REDIS, reason="TEST_REDIS_URL non défini")
async def test_real_quotes_us_and_europe_with_cache(monkeypatch):
    monkeypatch.setenv("REDIS_URL", os.environ["TEST_REDIS_URL"])
    import investia.cache as redis_module

    redis_module._redis = None

    settings = Settings(_env_file=None)
    service = build_market_service(settings)

    q_us = await service.get_quote("AAPL")
    assert q_us.source == "finnhub"
    assert q_us.value > 0
    assert q_us.currency == "USD"

    from investia.market.base import MarketDataError

    try:
        q_eu = await service.get_quote("SAP.DE")
    except MarketDataError as err:
        if "429" in str(err):
            pytest.skip(
                "Yahoo rate-limite cette IP (risque P8) — couvert par les tests mockés"
            )
        raise
    assert q_eu.source == "yahoo"
    assert q_eu.value > 0
    assert q_eu.currency == "EUR"
    assert q_eu.delayed is True

    # Le 2e appel US vient du cache Redis : même valeur, sans nouvel appel réseau.
    q_us_cached = await service.get_quote("AAPL")
    assert q_us_cached == q_us

    fx = await service.get_quote("USD")
    assert fx.source == "frankfurter"
    assert 0 < fx.value < 2

    redis_module._redis = None
