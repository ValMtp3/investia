"""Connecteur Yahoo Finance (chart API) — Europe (XETRA, Euronext) et historique.

API non officielle (ToS gris, P8) : isolée ici, swappable sans toucher le reste.
Les prix sont delayed (~15 min) : `delayed=True` sur chaque MarketData.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from investia.market.base import MarketData, MarketDataError

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


class YahooConnector:
    name = "yahoo"

    def __init__(
        self, client: httpx.AsyncClient | None = None, retry_delay: float = 2.0
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": USER_AGENT}
        )
        self._retry_delay = retry_delay

    async def _chart(self, symbol: str, range_: str, interval: str) -> dict[str, Any]:
        response = None
        for attempt in range(2):
            response = await self._client.get(
                f"{BASE_URL}/{symbol}", params={"range": range_, "interval": interval}
            )
            if response.status_code == 429 and attempt == 0:
                await asyncio.sleep(self._retry_delay)
                continue
            break
        if response is None or response.status_code != 200:
            status = response.status_code if response is not None else "no response"
            raise MarketDataError(self.name, f"HTTP {status} pour {symbol}")
        payload = response.json()
        chart = payload.get("chart", {})
        if chart.get("error"):
            raise MarketDataError(self.name, str(chart["error"]))
        result = chart.get("result") or []
        if not result:
            raise MarketDataError(self.name, f"symbole inconnu : {symbol}")
        return result[0]

    async def get_quote(self, symbol: str) -> MarketData:
        meta = (await self._chart(symbol, "5d", "1d"))["meta"]
        return MarketData(
            value=float(meta["regularMarketPrice"]),
            currency=meta.get("currency", "EUR"),
            source=self.name,
            timestamp=datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=UTC),
            delayed=True,
        )

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        result = await self._chart(symbol, f"{days}d", "1d")
        currency = result["meta"].get("currency", "EUR")
        timestamps = result.get("timestamp", [])
        closes = result["indicators"]["quote"][0].get("close", [])
        return [
            MarketData(
                value=float(close),
                currency=currency,
                source=self.name,
                timestamp=datetime.fromtimestamp(int(ts), tz=UTC),
                delayed=True,
            )
            for ts, close in zip(timestamps, closes)
            if close is not None
        ]

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        raise MarketDataError(self.name, "news non disponible via l'API chart")
