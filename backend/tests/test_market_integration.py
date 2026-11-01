"""Tests d'intégration réels des connecteurs (réseau + vraies clés + vrai Redis)."""

import os

import pytest

from investia.config import Settings
from investia.market import build_market_service

pytestmark = pytest.mark.integration

HAS_FINNHUB = bool(os.environ.get("FINNHUB_API_KEY"))
HAS_EODHD = bool(os.environ.get("EODHD_API_KEY"))
HAS_TWELVEDATA = bool(os.environ.get("TWELVEDATA_API_KEY"))
HAS_MASSIVE = bool(os.environ.get("MASSIVE_API_KEY"))
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


@pytest.mark.skipif(not HAS_EODHD, reason="EODHD_API_KEY manquante")
@pytest.mark.skipif(not HAS_REDIS, reason="TEST_REDIS_URL non défini")
async def test_real_history_europe_via_eodhd(monkeypatch):
    monkeypatch.setenv("REDIS_URL", os.environ["TEST_REDIS_URL"])
    monkeypatch.setenv("EODHD_API_KEY", os.environ["EODHD_API_KEY"])
    import investia.cache as redis_module

    redis_module._redis = None

    settings = Settings(_env_file=None)
    service = build_market_service(settings)
    history = await service.get_history("SAP.DE", days=10)
    assert len(history) > 0
    assert all(h.source == "eodhd" for h in history)
    assert all(h.currency == "EUR" for h in history)

    redis_module._redis = None


@pytest.mark.skipif(not HAS_TWELVEDATA, reason="TWELVEDATA_API_KEY manquante")
async def test_real_history_us_via_twelvedata():
    from pydantic import SecretStr

    from investia.market.twelvedata import TwelveDataConnector

    connector = TwelveDataConnector(api_key=SecretStr(os.environ["TWELVEDATA_API_KEY"]))
    history = await connector.get_history("AAPL", days=10)
    assert len(history) > 0
    assert all(h.source == "twelvedata" and h.value > 0 for h in history)
    assert all(h.currency == "USD" for h in history)
    dates = [h.timestamp for h in history]
    assert dates == sorted(dates), "du plus ancien au plus récent"


@pytest.mark.skipif(not HAS_MASSIVE, reason="MASSIVE_API_KEY manquante")
async def test_real_history_us_via_massive():
    from pydantic import SecretStr

    from investia.market.massive import MassiveConnector

    connector = MassiveConnector(api_key=SecretStr(os.environ["MASSIVE_API_KEY"]))
    history = await connector.get_history("AAPL", days=10)
    assert 0 < len(history) <= 10
    assert all(h.source == "massive" and h.value > 0 for h in history)
    dates = [h.timestamp for h in history]
    assert dates == sorted(dates), "du plus ancien au plus récent"
