"""Outil get_indicators — moyennes mobiles et volatilité, calculées EN CODE (Polars).

L'IA ne calcule jamais : elle appelle cet outil et commente le résultat.
"""

import math
from typing import Any

import polars as pl
from pydantic import Field

from investia.market.base import MarketDataError, MarketDataService
from investia.tools.base import BaseTool, SymbolArgs, ToolError

TRADING_DAYS_PER_YEAR = 252


class IndicatorsArgs(SymbolArgs):
    days: int = Field(60, ge=30, le=400)


class GetIndicatorsTool(BaseTool[IndicatorsArgs]):
    name = "get_indicators"
    description = (
        "Indicateurs techniques d'un actif, calculés par le code sur l'historique : "
        "moyennes mobiles 20 et 50 jours (SMA) et volatilité annualisée sur 30 jours."
    )
    args_schema = IndicatorsArgs

    def __init__(self, market: MarketDataService) -> None:
        self._market = market

    async def run(self, args: IndicatorsArgs) -> dict[str, Any]:
        symbol = args.symbol.strip().upper()
        try:
            history = await self._market.get_history(symbol, days=args.days)
        except MarketDataError as error:
            raise ToolError(self.name, str(error)) from error
        if len(history) < 30:
            raise ToolError(
                self.name, f"historique insuffisant : {len(history)} points (< 30)"
            )
        closes = pl.Series("close", [point.value for point in history])
        returns = closes.pct_change().drop_nulls()
        std = returns.std()
        volatility = std * math.sqrt(TRADING_DAYS_PER_YEAR) if std is not None else None
        return {
            "symbol": symbol,
            "points": len(history),
            "source": history[0].source,
            "as_of": history[-1].timestamp.isoformat(),
            "sma20": closes.tail(20).mean(),
            "sma50": closes.tail(50).mean() if len(history) >= 50 else None,
            "volatility_30d_annualized": volatility,
        }
