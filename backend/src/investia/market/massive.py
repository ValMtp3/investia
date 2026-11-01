"""Connecteur Massive (ex-Polygon.io, plan Stocks Basic gratuit) — historique US.

Gratuit : 5 appels/minute, 2 ans de clôtures, actions US seulement. Quote et news
ne passent pas par cette source. La clé voyage dans l'en-tête `Authorization`
(Bearer), jamais dans l'URL.
Doc : https://massive.com/docs/rest/stocks/aggregates/custom-bars
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from pydantic import SecretStr

from investia.market.base import MarketData, MarketDataError

BASE_URL = "https://api.massive.com"
# Une journée de bourse ne couvre pas un jour calendaire : on demande une fenêtre
# deux fois plus large que `days`, puis on garde les `days` dernières clôtures.
WINDOW_FACTOR = 2


class MassiveConnector:
    name = "massive"

    def __init__(
        self, api_key: SecretStr, client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def get_quote(self, symbol: str) -> MarketData:
        raise MarketDataError(self.name, "quote non supporté (historique seulement)")

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        raise MarketDataError(self.name, "news non supporté")

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        end = date.today()
        start = end - timedelta(days=days * WINDOW_FACTOR)
        response = await self._client.get(
            f"{BASE_URL}/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc"},
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
        )
        if response.status_code != 200:
            raise MarketDataError(
                self.name,
                f"HTTP {response.status_code} pour {symbol}",
                rate_limited=response.status_code == 429,
            )
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            raise MarketDataError(self.name, f"aucune donnée pour {symbol}")
        return [
            MarketData(
                value=float(bar["c"]),
                currency="USD",
                source=self.name,
                timestamp=datetime.fromtimestamp(bar["t"] / 1000, tz=UTC),
                delayed=True,
            )
            for bar in results[-days:]
        ]
