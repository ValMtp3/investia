"""Façade MarketService : choisit la source (router) et met en cache (Redis TTL)."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from investia.market.base import (
    MarketData,
    MarketDataConnector,
    MarketDataError,
    SymbolHit,
)
from investia.market.cache import (
    cached,
    is_paused,
    pause,
    recall_failure,
    remember_failure,
)
from investia.market.router import pick_source, pick_sources

logger = logging.getLogger(__name__)

TTL_QUOTE = 60
# Une clôture ne change qu'une fois par jour : 24 h ménage les quotas gratuits.
TTL_HISTORY = 86400
# Un échec total est retenu 5 min : sans ça, chaque rafraîchissement relance toute la
# cascade (un symbole inconnu viderait le quota gratuit en quelques minutes).
TTL_FAILURE = 300
# Pause d'une source qui répond « trop de requêtes » (429).
PAUSE_SECONDS = 600
TTL_NEWS = 900
TTL_FX = 86400
# Les résultats de recherche changent peu : 24 h de cache ménage les quotas.
TTL_SEARCH = 86400
# Sources interrogées pour la recherche par nom, dans l'ordre (les autres lèvent
# « non supportée » et sont sautées).
SEARCH_SOURCES = ("finnhub", "yahoo", "coingecko")

# Erreurs qu'un connecteur peut laisser passer sans les convertir : réseau coupé,
# délai dépassé, JSON invalide, champ absent. Elles ne doivent pas casser la cascade.
UNEXPECTED_SOURCE_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError)

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
        source = pick_source(symbol, kind=kind)
        connector = self._connectors.get(source)
        if connector is None:
            raise MarketDataError(
                "router", f"connecteur {source!r} non configuré (clé API manquante ?)"
            )
        return connector

    async def _guarded[T](self, source: str, call: Callable[[], Awaitable[T]]) -> T:
        """Appelle une source en respectant sa pause ; un 429 la met en pause.

        Sans cache (donc sans Redis), il n'y a ni pause ni mémoire : appel direct.
        """
        if self._use_cache and await is_paused(source):
            raise MarketDataError(source, "en pause (trop de requêtes)")
        try:
            return await call()
        except MarketDataError as error:
            if error.rate_limited and self._use_cache:
                await pause(source, PAUSE_SECONDS)
            raise

    async def get_quote(self, symbol: str) -> MarketData:
        connector = self._connector_for(symbol, kind="quote")
        if not self._use_cache:
            return await connector.get_quote(symbol)
        raw = await cached(
            f"quote:{symbol.upper()}",
            ttl=TTL_QUOTE,
            factory=lambda: self._quote_dict(connector, symbol),
        )
        return MarketData.from_dict(raw)

    async def _quote_dict(
        self, connector: MarketDataConnector, symbol: str
    ) -> dict[str, Any]:
        quote = await self._guarded(connector.name, lambda: connector.get_quote(symbol))
        return quote.to_dict()

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        if not self._use_cache:
            return await self._history_from_sources(symbol, days)
        failure_key = f"history-failed:{symbol.upper()}:{days}"
        known_failure = await recall_failure(failure_key)
        if known_failure is not None:
            raise MarketDataError("historique", known_failure)
        try:
            raw = await cached(
                f"history:{symbol.upper()}:{days}",
                ttl=TTL_HISTORY,
                factory=lambda: self._history_dicts(symbol, days),
            )
        except MarketDataError as error:
            await remember_failure(failure_key, error.detail, TTL_FAILURE)
            raise
        return [MarketData.from_dict(item) for item in raw]

    async def _history_dicts(self, symbol: str, days: int) -> list[dict[str, Any]]:
        return [
            point.to_dict() for point in await self._history_from_sources(symbol, days)
        ]

    async def _history_from_sources(self, symbol: str, days: int) -> list[MarketData]:
        """Essaie les sources dans l'ordre (plan B, plan C…) : la première qui répond.

        Une source sans clé est sautée. Une source qui répond 429 est mise en pause
        (Redis) pour ne pas aggraver le blocage. Une réponse vide ou une erreur
        réseau/format compte comme un échec : on passe à la suivante. Si toutes
        échouent : une seule erreur qui liste chaque tentative, jamais de chiffre
        inventé.
        """
        attempts: list[str] = []
        for source in pick_sources(symbol, kind="history"):
            connector = self._connectors.get(source)
            if connector is None:
                attempts.append(f"{source}: non configuré (clé API manquante ?)")
                continue
            try:
                history = await self._guarded(
                    source, lambda: connector.get_history(symbol, days)
                )
            except MarketDataError as error:
                paused = error.rate_limited and self._use_cache
                attempts.append(f"{error}{' (en pause)' if paused else ''}")
                continue
            except UNEXPECTED_SOURCE_ERRORS as error:
                logger.warning(
                    "%s : erreur inattendue pour %s", source, symbol, exc_info=True
                )
                attempts.append(
                    f"{source}: erreur réseau ou format ({type(error).__name__})"
                )
                continue
            if not history:
                attempts.append(f"{source}: aucune donnée")
                continue
            return history
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

    async def search_symbols(self, query: str, limit: int = 10) -> list[SymbolHit]:
        """Recherche par nom, multi-sources : fusionne et dédoublonne par symbole.

        Les sources sans support lèvent MarketDataError « non supportée » et sont
        sautées ; si toutes échouent, une seule erreur qui liste les tentatives.
        """
        q = query.strip()
        if not self._use_cache:
            return await self._search_from_sources(q, limit)
        raw = await cached(
            f"search:{q.lower()}:{limit}",
            ttl=TTL_SEARCH,
            factory=lambda: self._search_uncached(q, limit),
        )
        return [SymbolHit(**item) for item in raw]

    async def _search_uncached(self, query: str, limit: int) -> list[dict[str, Any]]:
        return [hit.to_dict() for hit in await self._search_from_sources(query, limit)]

    async def _search_from_sources(self, query: str, limit: int) -> list[SymbolHit]:
        ordered = [s for s in SEARCH_SOURCES if s in self._connectors]
        ordered += [s for s in self._connectors if s not in SEARCH_SOURCES]
        attempts: list[str] = []
        seen: set[str] = set()
        merged: list[SymbolHit] = []
        for source in ordered:
            connector = self._connectors[source]
            search_fn = getattr(connector, "search_symbols", None)
            if search_fn is None:
                attempts.append(f"{source}: recherche non supportée")
                continue
            try:
                hits = await self._guarded(source, lambda: search_fn(query, limit))
            except MarketDataError as error:
                attempts.append(str(error))
                continue
            except UNEXPECTED_SOURCE_ERRORS as error:
                logger.warning("%s : erreur inattendue (search)", source, exc_info=True)
                attempts.append(
                    f"{source}: erreur réseau ou format ({type(error).__name__})"
                )
                continue
            for hit in hits:
                key = hit.symbol.upper()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(hit)
                if len(merged) >= limit:
                    return merged
        if not merged:
            raise MarketDataError(
                "recherche",
                f"aucun résultat pour {query!r} — " + " · ".join(attempts),
            )
        return merged
