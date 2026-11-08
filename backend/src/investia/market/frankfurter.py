"""Connecteur Frankfurter (taux officiels BCE/ECB) — sans clé, taux journaliers."""

from datetime import UTC, datetime
from typing import Any

import httpx

from investia.market.base import MarketData, MarketDataError, SymbolHit

BASE_URL = "https://api.frankfurter.dev/v1"


class FrankfurterConnector:
    name = "frankfurter"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def get_quote(self, symbol: str) -> MarketData:
        """`symbol` = devise de base (ex. "USD") -> taux vers EUR du jour."""
        base = symbol.upper()
        response = await self._client.get(
            f"{BASE_URL}/latest", params={"from": base, "to": "EUR"}
        )
        if response.status_code != 200:
            raise MarketDataError(self.name, f"HTTP {response.status_code} pour {base}")
        payload = response.json()
        if "rates" not in payload or "EUR" not in payload["rates"]:
            raise MarketDataError(self.name, f"taux indisponible pour {base}")
        return MarketData(
            value=float(payload["rates"]["EUR"]),
            currency="EUR",
            source=self.name,
            timestamp=datetime.fromisoformat(payload["date"]).replace(tzinfo=UTC),
        )

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        from datetime import date, timedelta

        base = symbol.upper()
        end = date.today()
        start = end - timedelta(days=days)
        response = await self._client.get(
            f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}",
            params={"from": base, "to": "EUR"},
        )
        if response.status_code != 200:
            raise MarketDataError(
                self.name, f"HTTP {response.status_code} pour historique {base}"
            )
        rates = response.json().get("rates", {})
        return [
            MarketData(
                value=float(day_rates["EUR"]),
                currency="EUR",
                source=self.name,
                timestamp=datetime.fromisoformat(day).replace(tzinfo=UTC),
            )
            for day, day_rates in sorted(rates.items())
        ]

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        raise MarketDataError(self.name, "pas de news sur un taux de change")

    async def search_symbols(self, query: str, limit: int = 10) -> list[SymbolHit]:
        raise MarketDataError(self.name, "recherche de symboles non supportée")
