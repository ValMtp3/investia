"""Service de backtest : rejoue les ordres simulés sur l'historique (étape 10, D67).

Lit les ordres + ajustements en base, récupère les clôtures journalières via le
MarketService (symboles, indice CW8.PA, taux de change Frankfurter), appelle le
moteur pur `portfolio/backtest.py` et renvoie un dict JSON-ready.

Résultat caché 24 h en Redis (comme l'historique de marché) : le calcul refait
les mêmes appels de sources, inutiles à moins d'un jour d'intervalle.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.market.base import MarketDataError, MarketDataService
from investia.market.cache import cached
from investia.portfolio.backtest import (
    BENCHMARK_SYMBOL,
    BacktestAdjustment,
    BacktestOrder,
    PriceSeries,
    run_backtest,
)

TTL_BACKTEST = 86400  # 24 h, comme l'historique de marché
CACHE_KEY = "backtest:v1"


class BacktestService:
    def __init__(
        self,
        session_factory: async_sessionmaker | None,
        market: MarketDataService,
        use_cache: bool = True,
    ) -> None:
        # session_factory=None : jamais de lecture en base (tests du moteur seul).
        self._session_factory = session_factory
        self._market = market
        self._use_cache = use_cache

    async def compute(self) -> dict[str, Any]:
        if self._use_cache:
            return await cached(CACHE_KEY, TTL_BACKTEST, self._compute_uncached)
        return await self._compute_uncached()

    async def _load_events(
        self,
    ) -> tuple[list[BacktestOrder], list[BacktestAdjustment]]:
        if self._session_factory is None:
            raise RuntimeError(
                "BacktestService sans session_factory : aucun ordre en base"
            )
        async with self._session_factory() as session:
            row = await session.execute(text("SELECT id FROM portfolios LIMIT 1"))
            portfolio_id = row.scalar_one_or_none()
            if portfolio_id is None:
                return [], []
            orders_rows = (
                await session.execute(
                    text(
                        "SELECT symbol, side, quantity, created_at FROM orders "
                        "WHERE portfolio_id = :pid ORDER BY created_at, id"
                    ),
                    {"pid": portfolio_id},
                )
            ).all()
            adj_rows = (
                await session.execute(
                    text(
                        "SELECT amount, created_at FROM capital_adjustments "
                        "WHERE portfolio_id = :pid ORDER BY created_at, id"
                    ),
                    {"pid": portfolio_id},
                )
            ).all()
        orders = [
            BacktestOrder(
                date=created_at.date().isoformat(),
                symbol=symbol,
                side=side,
                quantity=float(quantity),
            )
            for symbol, side, quantity, created_at in orders_rows
        ]
        adjustments = [
            BacktestAdjustment(date=created_at.date().isoformat(), amount=float(amount))
            for amount, created_at in adj_rows
        ]
        return orders, adjustments

    def _series_from_history(self, symbol: str, history: list) -> PriceSeries:
        closes = {
            point.timestamp.date().isoformat(): float(point.value) for point in history
        }
        currency = history[0].currency if history else "EUR"
        return PriceSeries(symbol=symbol, currency=currency, closes=closes)

    async def _compute_uncached(self) -> dict[str, Any]:
        orders, adjustments = await self._load_events()
        if not orders and not adjustments:
            return {
                "start_date": None,
                "initial_capital": 0.0,
                "benchmark_symbol": BENCHMARK_SYMBOL,
                "points": [],
                "perf_portfolio_pct": 0.0,
                "perf_benchmark_pct": 0.0,
                "warnings": ["Aucun ordre ni ajustement de capital pour l'instant."],
                "generated_at": datetime.now(UTC).isoformat(),
            }

        # Départ = date du 1er ajustement de capital, sinon du 1er ordre.
        event_dates = [a.date for a in adjustments] + [o.date for o in orders]
        start_date = min(event_dates)
        days = (date.today() - date.fromisoformat(start_date)).days + 30

        warnings: list[str] = []
        series: dict[str, PriceSeries] = {}
        for symbol in sorted({o.symbol for o in orders}):
            try:
                history = await self._market.get_history(symbol, days)
            except MarketDataError as error:
                warnings.append(f"{symbol}: historique indisponible ({error})")
                continue
            if not history:
                warnings.append(f"{symbol}: historique vide")
                continue
            series[symbol] = self._series_from_history(symbol, history)

        # Indice de référence (CW8.PA) : échec total -> 503 (pas de comparaison).
        benchmark_history = await self._market.get_history(BENCHMARK_SYMBOL, days)
        if not benchmark_history:
            raise MarketDataError(
                "backtest", f"historique de l'indice {BENCHMARK_SYMBOL} vide"
            )
        benchmark = self._series_from_history(BENCHMARK_SYMBOL, benchmark_history)

        # Taux de change journaliers pour chaque devise étrangère rencontrée.
        currencies = {s.currency for s in series.values()}
        currencies.add(benchmark.currency)
        fx: dict[str, dict[str, float]] = {}
        for currency in sorted(currencies - {"EUR"}):
            try:
                fx_history = await self._market.get_history(currency, days)
                fx[currency] = {
                    point.timestamp.date().isoformat(): float(point.value)
                    for point in fx_history
                }
            except MarketDataError as error:
                warnings.append(f"taux {currency}->EUR indisponible ({error})")

        result = run_backtest(
            orders=orders,
            adjustments=adjustments,
            series=series,
            benchmark=benchmark,
            fx=fx,
            start_date=start_date,
        )
        warnings.extend(result.warnings)
        return {
            "start_date": result.start_date,
            "initial_capital": result.initial_capital,
            "benchmark_symbol": result.benchmark_symbol,
            "points": [
                {
                    "date": p.date,
                    "portfolio_value": p.portfolio_value,
                    "benchmark_value": p.benchmark_value,
                }
                for p in result.points
            ],
            "perf_portfolio_pct": result.perf_portfolio_pct,
            "perf_benchmark_pct": result.perf_benchmark_pct,
            "warnings": warnings,
            "generated_at": datetime.now(UTC).isoformat(),
        }
