"""Service portefeuille simulé — persistance SQL + valorisation marché.

Tous les calculs passent par portfolio.calc (code pur), jamais par le LLM.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.market.base import MarketDataService
from investia.portfolio.calc import InsufficientFunds, apply_order

DEFAULT_CAPITAL_EUR = 10_000.0


class PortfolioService:
    def __init__(
        self, session_factory: async_sessionmaker, market: MarketDataService
    ) -> None:
        self._session_factory = session_factory
        self._market = market

    async def ensure_default_portfolio(self) -> str:
        """Crée le portefeuille par défaut (10 000 €). Renvoie son id."""
        async with self._session_factory() as session:
            row = await session.execute(text("SELECT id::text FROM portfolios LIMIT 1"))
            existing = row.scalar_one_or_none()
            if existing:
                return existing
            result = await session.execute(
                text(
                    "INSERT INTO portfolios (name, currency, cash) "
                    "VALUES ('principal', 'EUR', :cash) RETURNING id::text"
                ),
                {"cash": DEFAULT_CAPITAL_EUR},
            )
            portfolio_id = result.scalar_one()
            await session.execute(
                text(
                    "INSERT INTO capital_adjustments (portfolio_id, amount, reason) "
                    "VALUES (:pid, :amount, 'capital initial')"
                ),
                {"pid": UUID(portfolio_id), "amount": DEFAULT_CAPITAL_EUR},
            )
            await session.commit()
            return portfolio_id

    async def _get_cash(self, session, portfolio_id: str) -> float:
        row = await session.execute(
            text("SELECT cash FROM portfolios WHERE id = :pid"),
            {"pid": UUID(portfolio_id)},
        )
        return float(row.scalar_one())

    async def _get_position(
        self, session, portfolio_id: str, symbol: str
    ) -> tuple[float, float]:
        row = await session.execute(
            text(
                "SELECT quantity, avg_price FROM positions "
                "WHERE portfolio_id = :pid AND symbol = :s"
            ),
            {"pid": UUID(portfolio_id), "s": symbol},
        )
        result = row.first()
        if result is None:
            return 0.0, 0.0
        return float(result[0]), float(result[1])

    async def price_eur(self, symbol: str) -> Any:
        """Dernier prix connu converti en EUR (taux Frankfurter si besoin)."""
        quote = await self._market.get_quote(symbol)
        if quote.currency == "EUR":
            return quote, quote.value
        fx = await self._market.get_quote(quote.currency)  # ex. "USD" -> EUR
        return quote, quote.value * fx.value

    async def place_order(
        self, symbol: str, side: str, quantity: float
    ) -> dict[str, Any]:
        quote, price_eur = await self.price_eur(symbol)
        async with self._session_factory() as session:
            portfolio_id = await self.ensure_default_portfolio()
            cash = await self._get_cash(session, portfolio_id)
            position_qty, position_avg = await self._get_position(
                session, portfolio_id, symbol
            )
            try:
                new_state = apply_order(
                    cash=cash,
                    position_qty=position_qty,
                    position_avg=position_avg,
                    side=side,
                    quantity=quantity,
                    price_eur=price_eur,
                )
            except InsufficientFunds as error:
                raise InsufficientFunds(str(error)) from error
            await session.execute(
                text("UPDATE portfolios SET cash = :cash WHERE id = :pid"),
                {"cash": new_state.cash, "pid": UUID(portfolio_id)},
            )
            await session.execute(
                text(
                    "INSERT INTO positions (portfolio_id, symbol, quantity, avg_price) "
                    "VALUES (:pid, :s, :q, :a) "
                    "ON CONFLICT (portfolio_id, symbol) DO UPDATE SET "
                    "quantity = :q, avg_price = :a, updated_at = now()"
                ),
                {
                    "pid": UUID(portfolio_id),
                    "s": symbol,
                    "q": new_state.position_qty,
                    "a": new_state.position_avg,
                },
            )
            result = await session.execute(
                text(
                    "INSERT INTO orders (portfolio_id, symbol, side, quantity, "
                    "price, fee) VALUES (:pid, :s, :side, :q, :p, :f) "
                    "RETURNING id::text"
                ),
                {
                    "pid": UUID(portfolio_id),
                    "s": symbol,
                    "side": side,
                    "q": quantity,
                    "p": price_eur,
                    "f": new_state.fee,
                },
            )
            order_id = result.scalar_one()
            await session.commit()
            return {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price_eur": price_eur,
                "fee": new_state.fee,
                "cash_after": new_state.cash,
                "price_source": quote.source,
                "price_timestamp": quote.timestamp.isoformat(),
            }

    async def adjust_capital(self, amount: float, reason: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            portfolio_id = await self.ensure_default_portfolio()
            await session.execute(
                text(
                    "INSERT INTO capital_adjustments (portfolio_id, amount, reason) "
                    "VALUES (:pid, :amount, :reason)"
                ),
                {"pid": UUID(portfolio_id), "amount": amount, "reason": reason},
            )
            await session.execute(
                text("UPDATE portfolios SET cash = cash + :amount WHERE id = :pid"),
                {"amount": amount, "pid": UUID(portfolio_id)},
            )
            row = await session.execute(
                text("SELECT cash FROM portfolios WHERE id = :pid"),
                {"pid": UUID(portfolio_id)},
            )
            cash = float(row.scalar_one())
            await session.commit()
            return {"cash": cash, "adjustment": amount, "reason": reason}

    async def get_portfolio(self) -> dict[str, Any]:
        async with self._session_factory() as session:
            portfolio_id = await self.ensure_default_portfolio()
            cash = await self._get_cash(session, portfolio_id)
            rows = (
                await session.execute(
                    text(
                        "SELECT symbol, quantity, avg_price FROM positions "
                        "WHERE portfolio_id = :pid ORDER BY symbol"
                    ),
                    {"pid": UUID(portfolio_id)},
                )
            ).all()
        positions = []
        total_positions = 0.0
        for symbol, quantity, avg_price in rows:
            quote, price_eur = await self.price_eur(symbol)
            value = float(quantity) * price_eur
            total_positions += value
            positions.append(
                {
                    "symbol": symbol,
                    "quantity": float(quantity),
                    "avg_price": float(avg_price),
                    "price_eur": price_eur,
                    "value_eur": value,
                    "source": quote.source,
                    "price_timestamp": quote.timestamp.isoformat(),
                }
            )
        return {
            "cash": cash,
            "positions": positions,
            "positions_value": total_positions,
            "total_value": cash + total_positions,
            "currency": "EUR",
        }
