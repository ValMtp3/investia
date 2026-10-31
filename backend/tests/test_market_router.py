"""Tests du routeur : quel connecteur pour quel symbole ?"""

from investia.market.router import pick_source


def test_us_symbol_goes_to_finnhub():
    assert pick_source("AAPL") == "finnhub"
    assert pick_source("MSFT") == "finnhub"


def test_european_symbols_go_to_yahoo():
    assert pick_source("SAP.DE") == "yahoo"
    assert pick_source("AIR.PA") == "yahoo"
    assert pick_source("VWCE.DE") == "yahoo"


def test_crypto_symbol_goes_to_coingecko():
    assert pick_source("BTC-USD") == "coingecko"
    assert pick_source("ETH-USD") == "coingecko"


def test_fx_pair_goes_to_frankfurter():
    assert pick_source("EURUSD") == "frankfurter"
    assert pick_source("USD") == "frankfurter"


def test_history_europe_goes_to_eodhd():
    assert pick_source("SAP.DE", kind="history") == "eodhd"
    assert pick_source("AIR.PA", kind="history") == "eodhd"


def test_history_us_goes_to_yahoo():
    assert pick_source("AAPL", kind="history") == "yahoo"


def test_news_goes_to_finnhub():
    assert pick_source("AAPL", kind="news") == "finnhub"
