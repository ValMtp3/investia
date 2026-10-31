"""Façade MarketService : choisit la source (router) et met en cache (Redis TTL)."""

from typing import Any

from investia.market.base import MarketData, MarketDataConnector
from investia.market.cache import cached
from investia.market.router import pick_source

TTL_QUOTE = 60
TTL_HISTORY = 3600
TTL_NEWS = 900
TTL_FX = 86400

_TTL_BY_METHOD = {
    "quote": TTL_QUOTE,
    "history": TTL_HISTORY,
    "news": TTL_NEWS,
    "fx": TTL_FX,
}


class MarketService:
    """Point d'entrée unique pour les données de marché."""

    def __init__(
        self, connectors: dict[str, MarketDataConnector], use_cache: bool = True
    ) -> None:
        self._connectors = connectors
        self._use_cache = use_cache

    def _connector_for(self, symbol: str) -> MarketDataConnector:
        from investia.market.base import MarketDataError

        source = pick_source(symbol)
        connector = self._connectors.get(source)
        if connector is None:
            raise MarketDataError(
                "router", f"connecteur {source!r} non configuré (clé API manquante ?)"
            )
        return connector

    async def get_quote(self, symbol: str) -> MarketData:
        connector = self._connector_for(symbol)
        if not self._use_cache:
            return await connector.get_quote(symbol)
        raw = await cached(
            f"quote:{symbol.upper()}",
            ttl=TTL_QUOTE,
            factory=lambda: _quote_dict(connector, symbol),
        )
        return MarketData.from_dict(raw)

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        connector = self._connector_for(symbol)
        if not self._use_cache:
            return await connector.get_history(symbol, days)
        raw = await cached(
            f"history:{symbol.upper()}:{days}",
            ttl=TTL_HISTORY,
            factory=lambda: _history_dicts(connector, symbol, days),
        )
        return [MarketData.from_dict(item) for item in raw]

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        connector = self._connector_for(symbol)
        if not self._use_cache:
            return await connector.get_news(symbol, limit)
        return await cached(
            f"news:{symbol.upper()}:{limit}",
            ttl=TTL_NEWS,
            factory=lambda: connector.get_news(symbol, limit),
        )


async def _quote_dict(connector: MarketDataConnector, symbol: str) -> dict[str, Any]:
    return (await connector.get_quote(symbol)).to_dict()


async def _history_dicts(
    connector: MarketDataConnector, symbol: str, days: int
) -> list[dict[str, Any]]:
    return [point.to_dict() for point in await connector.get_history(symbol, days)]
