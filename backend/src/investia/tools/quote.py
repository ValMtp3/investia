"""Outil get_quote — prix actuel d'un actif, via MarketService."""

from typing import Any

from investia.market.base import MarketDataError, MarketDataService
from investia.tools.base import BaseTool, SymbolArgs, ToolError


class QuoteArgs(SymbolArgs):
    pass


class GetQuoteTool(BaseTool[QuoteArgs]):
    name = "get_quote"
    description = (
        "Prix actuel (ou dernier connu) d'un actif : action/ETF US (AAPL), "
        "Europe (SAP.DE, AIR.PA), crypto (BTC-USD), ou taux de change (USD -> EUR). "
        "Retourne valeur, devise, source et horodatage."
    )
    args_schema = QuoteArgs

    def __init__(self, market: MarketDataService) -> None:
        self._market = market

    async def run(self, args: QuoteArgs) -> dict[str, Any]:
        symbol = args.symbol.strip().upper()
        try:
            return (await self._market.get_quote(symbol)).to_dict()
        except MarketDataError as error:
            raise ToolError(self.name, str(error)) from error
