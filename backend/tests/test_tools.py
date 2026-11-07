"""Tests des 4 outils de l'agent : get_quote, get_history, get_indicators, get_news."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from investia.market.base import MarketData, MarketDataError
from investia.tools.base import ToolError
from investia.tools.history import GetHistoryTool, HistoryArgs
from investia.tools.indicators import GetIndicatorsTool, IndicatorsArgs
from investia.tools.news import GetNewsTool, NewsArgs
from investia.tools.quote import GetQuoteTool, QuoteArgs


class FakeMarket:
    def __init__(self, quote=None, history=None, news=None, error=None):
        self._quote = quote
        self._history = history or []
        self._news = news or []
        self._error = error
        self.quote_symbols = []
        self.history_calls = []

    async def get_quote(self, symbol):
        self.quote_symbols.append(symbol)
        if self._error:
            raise self._error
        return self._quote

    async def get_history(self, symbol, days=30):
        self.history_calls.append((symbol, days))
        if self._error:
            raise self._error
        return self._history

    async def get_news(self, symbol, limit=5):
        if self._error:
            raise self._error
        return self._news[:limit]


def make_history(values, source="yahoo"):
    base = datetime(2026, 10, 31, tzinfo=UTC)
    return [
        MarketData(
            value=v,
            currency="EUR",
            source=source,
            timestamp=base - timedelta(days=len(values) - 1 - i),
        )
        for i, v in enumerate(values)
    ]


async def test_get_quote_normalizes_symbol_and_returns_sourced_dict():
    market = FakeMarket(
        quote=MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )
    )
    tool = GetQuoteTool(market)
    result = await tool.run(QuoteArgs(symbol="aapl"))
    assert market.quote_symbols == ["AAPL"]
    assert result["value"] == 344.63
    assert result["source"] == "finnhub"
    assert "timestamp" in result


async def test_get_quote_market_error_becomes_tool_error():
    market = FakeMarket(error=MarketDataError("finnhub", "HTTP 500"))
    with pytest.raises(ToolError, match="get_quote"):
        await GetQuoteTool(market).run(QuoteArgs(symbol="AAPL"))


def test_quote_args_reject_empty_symbol():
    with pytest.raises(ValidationError):
        QuoteArgs(symbol="  ")


async def test_get_history_returns_points_with_source():
    market = FakeMarket(history=make_history([100.0, 101.0, 102.0]))
    result = await GetHistoryTool(market).run(HistoryArgs(symbol="SAP.DE", days=30))
    assert result["points"] == 3
    assert result["source"] == "yahoo"
    assert result["history"][-1]["value"] == 102.0
    assert market.history_calls == [("SAP.DE", 30)]


async def test_get_indicators_computes_sma_and_volatility_in_code():
    # 60 jours à 100, le dernier à 110 : sma20 = (19*100 + 110)/20 = 100.5
    values = [100.0] * 59 + [110.0]
    market = FakeMarket(history=make_history(values))
    result = await GetIndicatorsTool(market).run(
        IndicatorsArgs(symbol="SAP.DE", days=60)
    )
    assert result["sma20"] == pytest.approx(100.5)
    assert result["sma50"] == pytest.approx((49 * 100 + 110) / 50)
    assert result["volatility_30d_annualized"] > 0
    assert result["points"] == 60
    assert result["source"] == "yahoo"


async def test_get_indicators_rejects_too_short_history():
    market = FakeMarket(history=make_history([100.0] * 10))
    with pytest.raises(ToolError, match="get_indicators"):
        args = IndicatorsArgs(symbol="SAP.DE", days=60)
        await GetIndicatorsTool(market).run(args)


async def test_get_news_returns_limited_items():
    market = FakeMarket(news=[{"headline": f"n{i}"} for i in range(8)])
    result = await GetNewsTool(market).run(NewsArgs(symbol="AAPL", limit=3))
    assert len(result["news"]) == 3
