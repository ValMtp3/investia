"""Calculs du portefeuille simulé — en code pur, jamais par le LLM (D35).

Règles : ordre exécuté au dernier prix connu, frais proportionnels 0,1 %,
fractions d'actions autorisées, prix converti en EUR si besoin.
"""

from dataclasses import dataclass

FEE_RATE = 0.001  # 0,1 % (D35)


class InsufficientFunds(Exception):
    """Cash insuffisant (buy) ou position insuffisante (sell)."""


@dataclass(frozen=True)
class PortfolioState:
    cash: float
    position_qty: float
    position_avg: float
    fee: float = 0.0

    @property
    def total(self) -> float:
        return self.cash + self.position_qty * self.position_avg


def apply_order(
    *,
    cash: float,
    position_qty: float,
    position_avg: float,
    side: str,
    quantity: float,
    price_eur: float,
) -> PortfolioState:
    """Applique un ordre simulé et renvoie le nouvel état."""
    if quantity <= 0:
        raise ValueError("quantité invalide")
    if price_eur <= 0:
        raise ValueError("prix invalide")
    amount = price_eur * quantity
    fee = round(amount * FEE_RATE, 2)
    if side == "buy":
        if cash < amount + fee:
            raise InsufficientFunds(
                f"cash {cash:.2f} insuffisant pour {amount + fee:.2f} (montant + frais)"
            )
        new_qty = position_qty + quantity
        new_avg = (
            (position_qty * position_avg + quantity * price_eur) / new_qty
            if new_qty
            else 0.0
        )
        return PortfolioState(
            cash=cash - amount - fee,
            position_qty=new_qty,
            position_avg=new_avg,
            fee=fee,
        )
    if side == "sell":
        if position_qty < quantity:
            raise InsufficientFunds(
                f"position {position_qty} insuffisante pour vendre {quantity}"
            )
        return PortfolioState(
            cash=cash + amount - fee,
            position_qty=position_qty - quantity,
            position_avg=position_avg,
            fee=fee,
        )
    raise ValueError(f"side inconnu : {side}")
