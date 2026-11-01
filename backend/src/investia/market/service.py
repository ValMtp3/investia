"""Façade MarketService : choisit la source (router) et met en cache (Redis TTL)."""

from typing import Any

from investia.market.base import MarketData, MarketDataConnector, MarketDataError
from investia.market.cache import cached, is_paused, pause
from investia.market.router import pick_source, pick_sources

TTL_QUOTE = 60
# Une clôture ne change qu'une fois par jour : 24 h ménage les quotas gratuits.
TTL_HISTORY = 86400
# Pause d'une source qui répond « trop de requêtes » (429).
PAUSE_SECONDS = 600
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

    def _connector_for(self, symbol: str, kind: str = "quote") -> MarketDataConnector:
        from investia.market.base import MarketDataError

        source = pick_source(symbol, kind=kind)
        connector = self._connectors.get(source)
        if connector is None:
            raise MarketDataError(
                "router", f"connecteur {source!r} non configuré (clé API manquante ?)"
            )
        return connector

    async def get_quote(self, symbol: str) -> MarketData:
        connector = self._connector_for(symbol, kind="quote")
        if not self._use_cache:
            return await connector.get_quote(symbol)
        raw = await cached(
            f"quote:{symbol.upper()}",
            ttl=TTL_QUOTE,
            factory=lambda: _quote_dict(connector, symbol),
        )
        return MarketData.from_dict(raw)

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        if not self._use_cache:
            return await self._history_from_sources(symbol, days)
        raw = await cached(
            f"history:{symbol.upper()}:{days}",
            ttl=TTL_HISTORY,
            factory=lambda: self._history_dicts(symbol, days),
        )
        return [MarketData.from_dict(item) for item in raw]

    async def _history_dicts(self, symbol: str, days: int) -> list[dict[str, Any]]:
        return [
            point.to_dict() for point in await self._history_from_sources(symbol, days)
        ]

    async def _history_from_sources(self, symbol: str, days: int) -> list[MarketData]:
        """Essaie les sources dans l'ordre (plan B, plan C…) : la première qui répond.

        Une source sans clé est sautée. Une source qui répond 429 est mise en pause
        (Redis) pour ne pas aggraver le blocage. Si toutes échouent : une seule erreur
        qui liste chaque tentative, jamais de chiffre inventé.
        """
        attempts: list[str] = []
        for source in pick_sources(symbol, kind="history"):
            connector = self._connectors.get(source)
            if connector is None:
                attempts.append(f"{source}: non configuré (clé API manquante ?)")
                continue
            if self._use_cache and await is_paused(source):
                attempts.append(f"{source}: en pause (trop de requêtes)")
                continue
            try:
                return await connector.get_history(symbol, days)
            except MarketDataError as error:
                paused = error.rate_limited and self._use_cache
                if paused:
                    await pause(source, PAUSE_SECONDS)
                attempts.append(f"{error}{' (en pause)' if paused else ''}")
        raise MarketDataError(
            "historique", f"{symbol.upper()} indisponible — " + " · ".join(attempts)
        )

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        connector = self._connector_for(symbol, kind="news")
        if not self._use_cache:
            return await connector.get_news(symbol, limit)
        return await cached(
            f"news:{symbol.upper()}:{limit}",
            ttl=TTL_NEWS,
            factory=lambda: connector.get_news(symbol, limit),
        )


async def _quote_dict(connector: MarketDataConnector, symbol: str) -> dict[str, Any]:
    return (await connector.get_quote(symbol)).to_dict()
