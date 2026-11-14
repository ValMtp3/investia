"""Tests 17a — prévision Timestral : MistralTimestralForecaster (MockTransport,
zéro réseau) + outil get_forecast + câblage build_tools."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from test_sse import FakeMarket

from investia.market.base import MarketData
from investia.market.forecast import ForecastError, MistralTimestralForecaster
from investia.tools import build_tools
from investia.tools.base import ToolError
from investia.tools.forecast import GetForecastTool

BASE = datetime(2026, 10, 1, tzinfo=UTC)


def make_history(n=10):
    return [
        MarketData(
            value=100.0 + i,
            currency="USD",
            source="finnhub",
            timestamp=BASE + timedelta(days=i),
        )
        for i in range(n)
    ]


class FakeMarketWithHistory(FakeMarket):
    def __init__(self, history):
        self._history = history

    async def get_history(self, symbol, days=30):
        return self._history[:days]


def canned_forecast_response(horizon=3):
    """Réponse type de l'API /v1/forecast : quantiles 0.1/0.5/0.9 par pas."""
    return {
        "model": "timestral-1-0-209m",
        "forecast": {
            "timestamps": [
                (BASE + timedelta(days=10 + i)).isoformat().replace("+00:00", "Z")
                for i in range(horizon)
            ],
            "quantiles": {
                "0.1": [90.0 + i for i in range(horizon)],
                "0.5": [100.0 + i for i in range(horizon)],
                "0.9": [110.0 + i for i in range(horizon)],
            },
        },
    }


def make_forecaster(handler, model="timestral-1-0-209m"):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MistralTimestralForecaster(
        api_key=SecretStr("mistral-test"),
        base_url="https://api.mistral.ai/v1",
        model=model,
        http_client=http,
    )


# --- client API ---------------------------------------------------------------


async def test_forecaster_posts_expected_body_and_parses_quantiles():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json=canned_forecast_response(horizon=3))

    forecaster = make_forecaster(handler)
    result = await forecaster.forecast(
        timestamps=[(BASE + timedelta(days=i)).isoformat() for i in range(10)],
        values=[100.0 + i for i in range(10)],
        horizon=3,
    )
    assert seen["url"] == "https://api.mistral.ai/v1/forecast"
    assert seen["auth"] == "Bearer mistral-test"
    import json

    body = json.loads(seen["body"])
    assert body["model"] == "timestral-1-0-209m"
    assert body["horizon"] == 3
    assert body["values"] == [100.0 + i for i in range(10)]
    assert len(body["timestamps"]) == 10
    assert body["quantiles"] == [0.1, 0.5, 0.9]

    assert result["horizon"] == 3
    assert result["median"] == [100.0, 101.0, 102.0]
    assert result["low"] == [90.0, 91.0, 92.0]
    assert result["high"] == [110.0, 111.0, 112.0]
    assert len(result["timestamps_forecast"]) == 3
    assert result["model"] == "timestral-1-0-209m"


async def test_forecaster_http_error_raises_forecast_error():
    def handler(request):
        return httpx.Response(500, json={"message": "boom"})

    forecaster = make_forecaster(handler)
    with pytest.raises(ForecastError, match="500"):
        await forecaster.forecast(["2026-10-01T00:00:00Z"], [1.0], 5)


async def test_forecaster_unexpected_json_raises_forecast_error():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    forecaster = make_forecaster(handler)
    with pytest.raises(ForecastError):
        await forecaster.forecast(["2026-10-01T00:00:00Z"], [1.0], 5)


# --- outil get_forecast --------------------------------------------------------


async def test_get_forecast_tool_returns_band_and_disclaimer():
    def handler(request):
        return httpx.Response(200, json=canned_forecast_response(horizon=2))

    tool = GetForecastTool(
        market=FakeMarketWithHistory(make_history(10)),
        forecaster=make_forecaster(handler),
    )
    result = await tool.run(tool.args_schema(symbol="aapl", days=10, horizon=2))
    assert result["symbol"] == "AAPL"
    assert result["horizon"] == 2
    assert result["median"] == [100.0, 101.0]
    assert result["low"] == [90.0, 91.0]
    assert result["high"] == [110.0, 111.0]
    assert "pas un conseil" in result["disclaimer"]
    assert (
        tool.untrusted_output is True
    )  # sortie API externe -> scan anti-injection (13b)


async def test_get_forecast_tool_rejects_short_history():
    def handler(request):  # ne doit jamais être appelé
        raise AssertionError("pas d'appel réseau si historique insuffisant")

    tool = GetForecastTool(
        market=FakeMarketWithHistory(make_history(3)),
        forecaster=make_forecaster(handler),
    )
    with pytest.raises(ToolError, match="historique"):
        await tool.run(tool.args_schema(symbol="AAPL", horizon=5))


async def test_get_forecast_tool_wraps_forecast_error():
    def handler(request):
        return httpx.Response(429, json={"message": "rate limited"})

    tool = GetForecastTool(
        market=FakeMarketWithHistory(make_history(10)),
        forecaster=make_forecaster(handler),
    )
    with pytest.raises(ToolError, match="429"):
        await tool.run(tool.args_schema(symbol="AAPL", horizon=5))


def test_get_forecast_tool_contract():
    tool = GetForecastTool(
        market=FakeMarketWithHistory([]),
        forecaster=make_forecaster(lambda r: httpx.Response(200, json={})),
    )
    spec = tool.to_openai_tool()
    assert spec["function"]["name"] == "get_forecast"
    params = spec["function"]["parameters"]
    assert params["type"] == "object"
    assert set(params["properties"]) == {"symbol", "days", "horizon"}
    assert "probabiliste" in tool.description


# --- câblage build_tools --------------------------------------------------------


def test_build_tools_wires_get_forecast_only_when_forecaster_provided():
    forecaster = make_forecaster(lambda r: httpx.Response(200, json={}))
    with_fc = build_tools(FakeMarket(), forecaster=forecaster)
    assert "get_forecast" in with_fc
    without_fc = build_tools(FakeMarket())
    assert "get_forecast" not in without_fc


async def test_forecaster_network_error_raises_forecast_error():
    """17a fix revue : une erreur réseau (timeout/DNS) ne doit pas fuiter brute."""

    def handler(request):
        raise httpx.ConnectError("connexion refusée", request=request)

    forecaster = make_forecaster(handler)
    with pytest.raises(ForecastError, match="impossible"):
        await forecaster.forecast(["2026-10-01T00:00:00Z"], [1.0], 5)


async def test_forecaster_non_json_200_raises_forecast_error():
    """17a fix revue : un 200 non-JSON ne doit pas lever JSONDecodeError brut."""

    def handler(request):
        return httpx.Response(
            200,
            content=b"<html>proxy error</html>",
            headers={"content-type": "text/html"},
        )

    forecaster = make_forecaster(handler)
    with pytest.raises(ForecastError, match="non JSON"):
        await forecaster.forecast(["2026-10-01T00:00:00Z"], [1.0], 5)
