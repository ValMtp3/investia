"""TDD étape 10 : moteur de backtest pur (sans réseau, sans base).

Contrat : les ordres sont rejoués à la clôture du jour (dernier prix connu si
trou), frais 0,1 % via le même apply_order que le réel (D35) ; les prix en
devise étrangère sont convertis au taux du jour (dernier taux connu si trou) ;
l'indice CW8.PA est acheté buy & hold au capital initial à la date de départ ;
le résultat donne une courbe journalière portefeuille vs indice + les perfs.
"""

from investia.portfolio.backtest import (
    BacktestAdjustment,
    BacktestOrder,
    PriceSeries,
    run_backtest,
)

BENCH = PriceSeries(
    symbol="CW8.PA",
    currency="EUR",
    closes={"2026-10-30": 100.0, "2026-10-31": 110.0, "2026-11-03": 121.0},
)
AAA = PriceSeries(
    symbol="AAA.PA",
    currency="EUR",
    closes={"2026-10-30": 100.0, "2026-10-31": 110.0, "2026-11-03": 121.0},
)
ADJ = [BacktestAdjustment(date="2026-10-30", amount=10_000.0)]


def test_buy_at_close_with_fee_and_benchmark_buy_hold():
    result = run_backtest(
        orders=[
            BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=10)
        ],
        adjustments=ADJ,
        series={"AAA.PA": AAA},
        benchmark=BENCH,
        fx={},
        start_date="2026-10-30",
        end_date="2026-11-03",
    )
    assert result.start_date == "2026-10-30"
    assert result.initial_capital == 10_000.0
    assert result.benchmark_symbol == "CW8.PA"
    by_date = {p.date: p for p in result.points}
    # 30/10 : achat 10 × 100 €, frais 0,1 % = 1 € → cash 8 999, valeur 8 999 + 1 000
    assert by_date["2026-10-30"].portfolio_value == 9_999.0
    assert by_date["2026-10-30"].benchmark_value == 10_000.0
    # 31/10 : prix 110 → 8 999 + 1 100 = 10 099 ; indice 10 000 × 110/100
    assert by_date["2026-10-31"].portfolio_value == 10_099.0
    assert by_date["2026-10-31"].benchmark_value == 11_000.0
    # 03/11 : prix 121 → 8 999 + 1 210 = 10 209 ; indice × 121/100
    assert by_date["2026-11-03"].portfolio_value == 10_209.0
    assert by_date["2026-11-03"].benchmark_value == 12_100.0
    assert result.perf_portfolio_pct == round((10_209.0 / 10_000.0 - 1) * 100, 4)
    assert result.perf_benchmark_pct == 21.0
    assert result.warnings == []


def test_sell_at_close_with_fee():
    result = run_backtest(
        orders=[
            BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=10),
            BacktestOrder(date="2026-10-31", symbol="AAA.PA", side="sell", quantity=5),
        ],
        adjustments=ADJ,
        series={"AAA.PA": AAA},
        benchmark=BENCH,
        fx={},
        start_date="2026-10-30",
        end_date="2026-10-31",
    )
    # vente 5 × 110 = 550 €, frais 0,55 € → cash 8 999 + 550 − 0,55 = 9 548,45
    # reste 5 actions × 110 → valeur = 9 548,45 + 550 = 10 098,45
    last = result.points[-1]
    assert last.date == "2026-10-31"
    assert abs(last.portfolio_value - 10_098.45) < 1e-6


def test_foreign_currency_converted_at_daily_fx_rate():
    aapl = PriceSeries(
        symbol="AAPL",
        currency="USD",
        closes={"2026-10-30": 200.0, "2026-10-31": 220.0},
    )
    bench = PriceSeries(
        symbol="CW8.PA",
        currency="EUR",
        closes={"2026-10-30": 100.0, "2026-10-31": 100.0},
    )
    result = run_backtest(
        orders=[
            BacktestOrder(date="2026-10-30", symbol="AAPL", side="buy", quantity=10)
        ],
        adjustments=ADJ,
        series={"AAPL": aapl},
        benchmark=bench,
        fx={"USD": {"2026-10-30": 0.9, "2026-10-31": 0.92}},
        start_date="2026-10-30",
        end_date="2026-10-31",
    )
    by_date = {p.date: p for p in result.points}
    # 30/10 : prix EUR = 200 × 0,9 = 180 → montant 1 800, frais 1,80 → cash 8 198,20
    assert abs(by_date["2026-10-30"].portfolio_value - (8_198.20 + 1_800.0)) < 1e-6
    # 31/10 : prix EUR = 220 × 0,92 = 202,40 → 8 198,20 + 2 024 = 10 222,20
    assert abs(by_date["2026-10-31"].portfolio_value - 10_222.20) < 1e-6


def test_missing_close_uses_last_known_price_and_warns():
    aaa = PriceSeries(
        symbol="AAA.PA",
        currency="EUR",
        closes={"2026-10-30": 100.0, "2026-11-03": 121.0},  # pas de clôture le 31/10
    )
    result = run_backtest(
        orders=[
            BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=10)
        ],
        adjustments=ADJ,
        series={"AAA.PA": aaa},
        benchmark=BENCH,
        fx={},
        start_date="2026-10-30",
        end_date="2026-11-03",
    )
    by_date = {p.date: p for p in result.points}
    assert set(by_date) == {
        "2026-10-30",
        "2026-10-31",
        "2026-11-03",
    }  # calendrier = union
    # 31/10 : dernier prix connu pour AAA = 100 → valeur 9 999 (indice 11 000)
    assert by_date["2026-10-31"].portfolio_value == 9_999.0
    assert any("AAA.PA" in w and "2026-10-31" in w for w in result.warnings)


def test_capital_adjustment_mid_period_changes_cash():
    result = run_backtest(
        orders=[
            BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=10)
        ],
        adjustments=ADJ + [BacktestAdjustment(date="2026-10-31", amount=-500.0)],
        series={"AAA.PA": AAA},
        benchmark=BENCH,
        fx={},
        start_date="2026-10-30",
        end_date="2026-10-31",
    )
    last = result.points[-1]
    # 31/10 : cash 8 999 − 500 = 8 499, + 10 × 110 = 9 599
    assert last.portfolio_value == 9_599.0


def test_order_skipped_with_warning_when_funds_insufficient_at_close():
    result = run_backtest(
        orders=[
            BacktestOrder(date="2026-10-30", symbol="AAA.PA", side="buy", quantity=200)
        ],
        adjustments=ADJ,
        series={"AAA.PA": AAA},
        benchmark=BENCH,
        fx={},
        start_date="2026-10-30",
        end_date="2026-10-30",
    )
    # 200 × 100 + frais = 20 020 € > 10 000 € → ordre ignoré, cash inchangé
    assert result.points[-1].portfolio_value == 10_000.0
    assert any("insuffisant" in w.lower() or "ignoré" in w for w in result.warnings)


def test_benchmark_base_is_first_known_close_when_start_has_none():
    bench = PriceSeries(
        symbol="CW8.PA",
        currency="EUR",
        closes={"2026-10-31": 110.0, "2026-11-03": 121.0},  # pas de clôture le 30/10
    )
    result = run_backtest(
        orders=[],
        adjustments=ADJ,
        series={},
        benchmark=bench,
        fx={},
        start_date="2026-10-30",
        end_date="2026-11-03",
    )
    by_date = {p.date: p for p in result.points}
    # base = 110 (31/10) : au 31/10 indice = 10 000, au 03/11 = 10 000 × 121/110
    assert by_date["2026-10-31"].benchmark_value == 10_000.0
    assert by_date["2026-11-03"].benchmark_value == round(10_000.0 * 121.0 / 110.0, 6)


def test_no_initial_capital_warns_and_perf_is_zero():
    result = run_backtest(
        orders=[],
        adjustments=[],
        series={},
        benchmark=BENCH,
        fx={},
        start_date="2026-10-30",
        end_date="2026-10-31",
    )
    assert result.initial_capital == 0.0
    assert result.perf_portfolio_pct == 0.0
    assert result.perf_benchmark_pct == 0.0
    assert any("capital" in w.lower() for w in result.warnings)
