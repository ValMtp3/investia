"""Outil get_history — historique des cours de clôture, via MarketService."""

from typing import Any

from pydantic import Field

from investia.market.base import MarketDataError, MarketDataService
from investia.tools.base import BaseTool, SymbolArgs, ToolError


class HistoryArgs(SymbolArgs):
    days: int = Field(30, ge=5, le=400)


class GetHistoryTool(BaseTool[HistoryArgs]):
    name = "get_history"
    description = (
        "Historique des cours de clôture journaliers d'un actif (jusqu'à 400 jours), "
        "avec source et horodatage de chaque point."
    )
    args_schema = HistoryArgs

    def __init__(self, market: MarketDataService) -> None:
        self._market = market

    async def run(self, args: HistoryArgs) -> dict[str, Any]:
        symbol = args.symbol.strip().upper()
        try:
            history = await self._market.get_history(symbol, days=args.days)
        except MarketDataError as error:
            raise ToolError(self.name, str(error)) from error
        return {
            "symbol": symbol,
            "points": len(history),
            "source": history[0].source if history else None,
            "history": [point.to_dict() for point in history],
        }
