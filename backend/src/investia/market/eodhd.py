"""Connecteur EODHD (plan Sandbox $0) — historique EOD Europe (XETRA, Euronext).

Gratuit : 20 appels/jour, 1 an d'historique, toutes places (60+). Le quote
live est payant en free : on lève une erreur claire plutôt qu'un faux prix.
Symbole : SAP.DE -> SAP.XETRA (EODHD), AIR.PA -> AIR.PA.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from investia.market.base import MarketData, MarketDataError, SymbolHit

BASE_URL = "https://eodhd.com/api"


def to_eodhd_symbol(symbol: str) -> str:
    upper = symbol.upper()
    if upper.endswith(".DE"):
        return upper[: -len(".DE")] + ".XETRA"
    if "." not in upper:
        return upper + ".US"  # action US : AAPL -> AAPL.US
    return upper


def currency_for(eodhd_symbol: str) -> str:
    """Devise de cotation : USD pour la place US, EUR pour XETRA et Euronext."""
    return "USD" if eodhd_symbol.endswith(".US") else "EUR"


class EodhdConnector:
    name = "eodhd"

    def __init__(
        self, api_key: SecretStr, client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def get_quote(self, symbol: str) -> MarketData:
        raise MarketDataError(self.name, "quote live payant en tier gratuit (Sandbox)")

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        eodhd_symbol = to_eodhd_symbol(symbol)
        response = await self._client.get(
            f"{BASE_URL}/eod/{eodhd_symbol}",
            params={
                "api_token": self._api_key.get_secret_value(),
                "period": "d",
                "fmt": "json",
                "order": "a",
            },
        )
        if response.status_code != 200:
            raise MarketDataError(
                self.name,
                f"HTTP {response.status_code} pour {eodhd_symbol}",
                rate_limited=response.status_code == 429,
            )
        rows = response.json()
        if not isinstance(rows, list):
            raise MarketDataError(self.name, f"réponse inattendue pour {eodhd_symbol}")
        points = rows[-days:] if days else rows
        return [
            MarketData(
                value=float(row["close"]),
                currency=currency_for(eodhd_symbol),
                source=self.name,
                timestamp=datetime.fromisoformat(row["date"]).replace(tzinfo=UTC),
                delayed=True,
            )
            for row in points
        ]

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        raise MarketDataError(self.name, "news non disponible via l'endpoint EOD free")

    async def search_symbols(self, query: str, limit: int = 10) -> list[SymbolHit]:
        raise MarketDataError(self.name, "recherche de symboles non supportée")
