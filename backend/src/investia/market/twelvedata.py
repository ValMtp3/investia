"""Connecteur Twelve Data (plan Basic gratuit) — historique des actions US.

Gratuit : 800 crédits/jour (1 crédit par symbole). Clôtures journalières seulement :
quote et news ne passent pas par cette source. La clé voyage dans l'en-tête
`Authorization`, jamais dans l'URL (qui finit dans les logs).
Doc : https://twelvedata.com/docs (endpoint /time_series).
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from investia.market.base import MarketData, MarketDataError

BASE_URL = "https://api.twelvedata.com"


class TwelveDataConnector:
    name = "twelvedata"

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
        response = await self._client.get(
            f"{BASE_URL}/time_series",
            params={"symbol": symbol, "interval": "1day", "outputsize": days},
            headers={"Authorization": f"apikey {self._api_key.get_secret_value()}"},
        )
        if response.status_code != 200:
            raise MarketDataError(
                self.name,
                f"HTTP {response.status_code} pour {symbol}",
                rate_limited=response.status_code == 429,
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise MarketDataError(self.name, f"réponse inattendue pour {symbol}")
        # Les erreurs de l'API arrivent parfois en HTTP 200 :
        # {"code", "message", "status"}.
        if payload.get("status") == "error":
            raise MarketDataError(
                self.name,
                f"{payload.get('message', 'erreur inconnue')} ({symbol})",
                rate_limited=payload.get("code") == 429,
            )
        values = payload.get("values")
        if not isinstance(values, list):
            raise MarketDataError(self.name, f"réponse inattendue pour {symbol}")
        if not values:
            raise MarketDataError(self.name, f"aucune donnée pour {symbol}")
        currency = (payload.get("meta") or {}).get("currency", "USD")
        points = [
            MarketData(
                value=float(row["close"]),
                currency=currency,
                source=self.name,
                timestamp=datetime.fromisoformat(row["datetime"]).replace(tzinfo=UTC),
                delayed=True,
            )
            for row in values
        ]
        # Twelve Data liste le plus récent d'abord : on remet l'ordre chronologique.
        return sorted(points, key=lambda point: point.timestamp)
