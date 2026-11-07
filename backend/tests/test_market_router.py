"""Tests du routeur : quel connecteur pour quel symbole ?"""

from investia.market.router import pick_source, pick_sources


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


def test_history_us_is_a_cascade_of_four_sources():
    assert pick_sources("AAPL", kind="history") == [
        "yahoo",
        "eodhd",
        "twelvedata",
        "massive",
    ]


def test_other_needs_keep_a_single_source():
    assert pick_sources("SAP.DE", kind="history") == ["eodhd"]
    assert pick_sources("BTC-USD", kind="history") == ["coingecko"]
    assert pick_sources("EURUSD", kind="history") == ["frankfurter"]
    assert pick_sources("AAPL", kind="quote") == ["finnhub"]
    assert pick_sources("SAP.DE", kind="quote") == ["yahoo"]


def test_pick_source_is_the_first_of_the_cascade():
    assert pick_source("AAPL", kind="history") == pick_sources("AAPL", "history")[0]
