"""Tests de la logique pure du portefeuille (calculs en code, zéro IO)."""

import pytest

from investia.portfolio.calc import InsufficientFunds, apply_order


def test_buy_updates_cash_position_and_fee():
    # 10 AAPL à 308.34 EUR, frais 0.1 %
    state = apply_order(
        cash=10_000.0,
        position_qty=0.0,
        position_avg=0.0,
        side="buy",
        quantity=10.0,
        price_eur=308.34,
    )
    amount = 10 * 308.34
    fee = round(amount * 0.001, 2)
    assert state.fee == pytest.approx(fee)
    assert state.cash == pytest.approx(10_000.0 - amount - fee)
    assert state.position_qty == 10.0
    assert state.position_avg == pytest.approx(308.34)
    assert state.total == pytest.approx(state.cash + 10 * 308.34)


def test_buy_averages_price_on_existing_position():
    state = apply_order(
        cash=5_000.0,
        position_qty=10.0,
        position_avg=300.0,
        side="buy",
        quantity=10.0,
        price_eur=320.0,
    )
    # prix moyen pondéré : (10*300 + 10*320) / 20 = 310
    assert state.position_avg == pytest.approx(310.0)
    assert state.position_qty == 20.0


def test_sell_credits_cash_and_keeps_avg():
    state = apply_order(
        cash=1_000.0,
        position_qty=10.0,
        position_avg=300.0,
        side="sell",
        quantity=4.0,
        price_eur=320.0,
    )
    amount = 4 * 320.0
    fee = amount * 0.001
    assert state.cash == pytest.approx(1_000.0 + amount - fee)
    assert state.position_qty == 6.0
    assert state.position_avg == pytest.approx(300.0)  # inchangé à la vente


def test_buy_without_enough_cash_raises():
    with pytest.raises(InsufficientFunds):
        apply_order(
            cash=100.0,
            position_qty=0.0,
            position_avg=0.0,
            side="buy",
            quantity=10.0,
            price_eur=308.34,
        )


def test_sell_more_than_position_raises():
    with pytest.raises(InsufficientFunds):
        apply_order(
            cash=1_000.0,
            position_qty=2.0,
            position_avg=300.0,
            side="sell",
            quantity=5.0,
            price_eur=320.0,
        )


def test_fractional_quantities_allowed():
    state = apply_order(
        cash=1_000.0,
        position_qty=0.0,
        position_avg=0.0,
        side="buy",
        quantity=0.5,
        price_eur=308.34,
    )
    assert state.position_qty == pytest.approx(0.5)
