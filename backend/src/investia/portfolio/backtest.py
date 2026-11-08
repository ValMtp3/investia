"""Backtest du portefeuille simulé vs indice de référence — moteur pur (D67).

Règles : les ordres sont rejoués à la clôture du jour de leur date (dernier prix
connu si trou de cotation), avec les mêmes frais 0,1 % que le réel (D35, via
`apply_order` de `portfolio/calc.py`). Les prix en devise étrangère sont
convertis au taux du jour (dernier taux connu si trou). L'indice de référence
(CW8.PA) est acheté « buy & hold » au capital initial à la date de départ.

Entrées/sorties en pur Python (dates AAAA-MM-JJ, qui se comparent
lexicographiquement = chronologiquement) : testable sans réseau ni base.
"""

from dataclasses import dataclass, field

from investia.portfolio.calc import InsufficientFunds, apply_order

BENCHMARK_SYMBOL = "CW8.PA"


@dataclass(frozen=True)
class BacktestOrder:
    date: str  # AAAA-MM-JJ
    symbol: str
    side: str  # "buy" | "sell"
    quantity: float


@dataclass(frozen=True)
class BacktestAdjustment:
    date: str  # AAAA-MM-JJ
    amount: float


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    currency: str
    closes: dict[str, float]  # date AAAA-MM-JJ -> clôture en devise native


@dataclass(frozen=True)
class BacktestPoint:
    date: str
    portfolio_value: float
    benchmark_value: float


@dataclass(frozen=True)
class BacktestResult:
    start_date: str
    initial_capital: float
    benchmark_symbol: str
    benchmark_currency: str
    points: list[BacktestPoint]
    perf_portfolio_pct: float
    perf_benchmark_pct: float
    warnings: list[str] = field(default_factory=list)


def _last_known(values: dict[str, float], date: str) -> float | None:
    """Dernière valeur connue à une date (clôture/ttaux du jour ou avant)."""
    candidates = [d for d in values if d <= date]
    if not candidates:
        return None
    return values[max(candidates)]


def run_backtest(
    *,
    orders: list[BacktestOrder],
    adjustments: list[BacktestAdjustment],
    series: dict[str, PriceSeries],
    benchmark: PriceSeries,
    fx: dict[str, dict[str, float]],  # devise -> {date: taux vers EUR}
    start_date: str,
    end_date: str | None = None,
) -> BacktestResult:
    """Rejoue les ordres sur l'historique et compare à l'indice buy & hold."""
    warnings: list[str] = []
    all_dates: set[str] = set()
    for one_series in [*series.values(), benchmark]:
        all_dates.update(one_series.closes)
    all_dates.update(o.date for o in orders)
    all_dates.update(a.date for a in adjustments)
    if end_date is None:
        end_date = max(all_dates) if all_dates else start_date
    calendar = sorted(d for d in all_dates if start_date <= d <= end_date)

    # Capital initial = ajustements du jour de départ (le « capital initial »
    # est enregistré comme un ajustement à sa création).
    initial_capital = sum(a.amount for a in adjustments if a.date == start_date)
    if initial_capital <= 0:
        warnings.append(
            f"aucun ajustement de capital à la date de départ {start_date} : "
            "capital initial = 0, perfs à 0"
        )

    # Base de l'indice : clôture au départ, sinon première clôture connue après.
    bench_base = _last_known(benchmark.closes, start_date)
    if bench_base is None:
        after = [d for d in benchmark.closes if d >= start_date]
        bench_base = benchmark.closes[min(after)] if after else None
    if bench_base is None or bench_base <= 0:
        warnings.append(
            f"{benchmark.symbol}: aucune clôture de l'indice, courbe à plat"
        )
        bench_base = None

    cash = 0.0
    positions: dict[str, tuple[float, float]] = {}  # symbole -> (quantité, prix moyen)
    points: list[BacktestPoint] = []

    for date in calendar:
        for adjustment in (a for a in adjustments if a.date == date):
            cash += adjustment.amount

        for order in (o for o in orders if o.date == date):
            one_series = series.get(order.symbol)
            close = _last_known(one_series.closes, date) if one_series else None
            rate = (
                1.0
                if one_series and one_series.currency == "EUR"
                else _last_known(fx.get(one_series.currency, {}), date)
                if one_series
                else None
            )
            if one_series is None or close is None:
                warnings.append(
                    f"{order.symbol}: aucune clôture connue au {date}, ordre ignoré"
                )
                continue
            if rate is None:
                warnings.append(
                    f"{order.symbol}: aucun taux {one_series.currency}->EUR connu au "
                    f"{date}, ordre ignoré"
                )
                continue
            if close != one_series.closes.get(date):
                warnings.append(
                    f"{order.symbol}: pas de clôture le {date}, "
                    "dernier prix connu utilisé"
                )
            price_eur = close * rate
            qty, avg = positions.get(order.symbol, (0.0, 0.0))
            try:
                new_state = apply_order(
                    cash=cash,
                    position_qty=qty,
                    position_avg=avg,
                    side=order.side,
                    quantity=order.quantity,
                    price_eur=price_eur,
                )
            except (InsufficientFunds, ValueError) as error:
                warnings.append(
                    f"{order.symbol} {order.side} {order.quantity} au {date}: "
                    f"ordre ignoré ({error})"
                )
                continue
            cash = new_state.cash
            positions[order.symbol] = (new_state.position_qty, new_state.position_avg)

        # Valorisation du portefeuille à cette date (dernier prix connu si trou).
        portfolio_value = cash
        for symbol, (qty, _avg) in positions.items():
            if qty <= 0:
                continue
            one_series = series[symbol]
            close = _last_known(one_series.closes, date)
            rate = (
                1.0
                if one_series.currency == "EUR"
                else _last_known(fx.get(one_series.currency, {}), date)
            )
            if close is None or rate is None:
                warnings.append(
                    f"{symbol}: pas de prix au {date}, "
                    "position valorisée à 0 dans le point"
                )
                continue
            if close != one_series.closes.get(date):
                warnings.append(
                    f"{symbol}: pas de clôture le {date}, dernier prix connu utilisé"
                )
            portfolio_value += qty * close * rate

        bench_close = _last_known(benchmark.closes, date)
        if bench_base and bench_close:
            benchmark_value = initial_capital * bench_close / bench_base
        else:
            benchmark_value = initial_capital

        points.append(
            BacktestPoint(
                date=date,
                portfolio_value=round(portfolio_value, 6),
                benchmark_value=round(benchmark_value, 6),
            )
        )

    if points and initial_capital > 0:
        perf_portfolio = (points[-1].portfolio_value / initial_capital - 1) * 100
        perf_benchmark = (points[-1].benchmark_value / initial_capital - 1) * 100
    else:
        perf_portfolio = 0.0
        perf_benchmark = 0.0

    return BacktestResult(
        start_date=start_date,
        initial_capital=initial_capital,
        benchmark_symbol=benchmark.symbol,
        benchmark_currency=benchmark.currency,
        points=points,
        perf_portfolio_pct=round(perf_portfolio, 4),
        perf_benchmark_pct=round(perf_benchmark, 4),
        warnings=warnings,
    )
