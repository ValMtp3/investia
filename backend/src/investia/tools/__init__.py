"""Registre des outils exposés à la boucle d'agent."""

from investia.market.base import MarketDataService
from investia.tools.base import BaseTool
from investia.tools.history import GetHistoryTool
from investia.tools.indicators import GetIndicatorsTool
from investia.tools.news import GetNewsTool
from investia.tools.quote import GetQuoteTool

__all__ = ["BaseTool", "build_tools"]


def build_tools(market: MarketDataService) -> dict[str, BaseTool]:
    """Construit les 4 outils branchés sur le service de données."""
    return {
        "get_quote": GetQuoteTool(market),
        "get_history": GetHistoryTool(market),
        "get_indicators": GetIndicatorsTool(market),
        "get_news": GetNewsTool(market),
    }
