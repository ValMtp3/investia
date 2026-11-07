"""Outil get_news — actualités récentes d'un actif (US, via Finnhub)."""

from typing import Any

from pydantic import Field

from investia.market.base import MarketDataError, MarketDataService
from investia.tools.base import BaseTool, SymbolArgs, ToolError


class NewsArgs(SymbolArgs):
    limit: int = Field(5, ge=1, le=20)


class GetNewsTool(BaseTool[NewsArgs]):
    name = "get_news"
    description = (
        "Actualités récentes sur un actif US (ex. AAPL). "
        "Pas de news gratuites pour l'Europe pour l'instant."
    )
    args_schema = NewsArgs

    def __init__(self, market: MarketDataService) -> None:
        self._market = market

    async def run(self, args: NewsArgs) -> dict[str, Any]:
        symbol = args.symbol.strip().upper()
        try:
            news = await self._market.get_news(symbol, limit=args.limit)
        except MarketDataError as error:
            raise ToolError(self.name, str(error)) from error
        return {"symbol": symbol, "news": news}
