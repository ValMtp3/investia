"""Connecteur Finnhub — prix temps réel US + news US (gratuit, 60 appels/min).

L'historique (candles) et la couverture Europe sont payants : on lève une
MarketDataError claire plutôt que de renvoyer un chiffre inventé.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from pydantic import SecretStr

from investia.market.base import MarketData, MarketDataError

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubConnector:
    name = "finnhub"

    def __init__(
        self, api_key: SecretStr, client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        params = {**params, "token": self._api_key.get_secret_value()}
        response = await self._client.get(f"{BASE_URL}{path}", params=params)
        if response.status_code != 200:
            raise MarketDataError(self.name, f"HTTP {response.status_code} pour {path}")
        data = response.json()
        if isinstance(data, dict) and "error" in data:
            raise MarketDataError(self.name, str(data["error"]))
        return data

    async def get_quote(self, symbol: str) -> MarketData:
        data = await self._get("/quote", {"symbol": symbol})
        return MarketData(
            value=float(data["c"]),
            currency="USD",
            source=self.name,
            timestamp=datetime.fromtimestamp(int(data["t"]), tz=UTC),
        )

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        raise MarketDataError(
            self.name, "historique (candle) payant sur le tier gratuit"
        )

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        today = date.today()
        data = await self._get(
            "/company-news",
            {
                "symbol": symbol,
                "from": (today - timedelta(days=7)).isoformat(),
                "to": today.isoformat(),
            },
        )
        return list(data[:limit])
