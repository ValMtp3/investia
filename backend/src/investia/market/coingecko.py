"""Connecteur CoinGecko Demo — crypto (prix et historique en EUR, clé demo gratuite)."""

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from investia.market.base import MarketData, MarketDataError

BASE_URL = "https://api.coingecko.com/api/v3"

# Symbole côté agent (BTC-USD) -> id CoinGecko (bitcoin)
COINGECKO_IDS = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
}


class CoinGeckoConnector:
    name = "coingecko"

    def __init__(
        self, api_key: SecretStr, client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    def _coin_id(self, symbol: str) -> str:
        coin_id = COINGECKO_IDS.get(symbol.upper())
        if coin_id is None:
            raise MarketDataError(self.name, f"crypto inconnue : {symbol}")
        return coin_id

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        params = {**params, "x_cg_demo_api_key": self._api_key.get_secret_value()}
        response = await self._client.get(f"{BASE_URL}{path}", params=params)
        if response.status_code != 200:
            raise MarketDataError(self.name, f"HTTP {response.status_code} pour {path}")
        return response.json()

    async def get_quote(self, symbol: str) -> MarketData:
        coin_id = self._coin_id(symbol)
        data = await self._get(
            "/simple/price", {"ids": coin_id, "vs_currencies": "eur"}
        )
        return MarketData(
            value=float(data[coin_id]["eur"]),
            currency="EUR",
            source=self.name,
            timestamp=datetime.now(tz=UTC),
            delayed=True,
        )

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        coin_id = self._coin_id(symbol)
        data = await self._get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": "eur", "days": days},
        )
        return [
            MarketData(
                value=float(price),
                currency="EUR",
                source=self.name,
                timestamp=datetime.fromtimestamp(ts / 1000, tz=UTC),
                delayed=True,
            )
            for ts, price in data.get("prices", [])
        ]

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        raise MarketDataError(self.name, "news crypto : endpoint à brancher plus tard")
