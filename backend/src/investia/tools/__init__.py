"""Registre des outils exposés à la boucle d'agent."""

from investia.market.base import MarketDataService
from investia.tools.base import BaseTool
from investia.tools.history import GetHistoryTool
from investia.tools.indicators import GetIndicatorsTool
from investia.tools.news import GetNewsTool
from investia.tools.order import SimulateOrderTool
from investia.tools.portfolio import GetPortfolioTool, PortfolioServiceLike
from investia.tools.quote import GetQuoteTool

__all__ = ["BaseTool", "build_tools"]


def build_tools(
    market: MarketDataService,
    memory_store=None,
    embeddings=None,
    portfolio_service: PortfolioServiceLike | None = None,
) -> dict[str, BaseTool]:
    """Les 4 outils marché, + mémoire si dispo, + portefeuille si service fourni."""
    tools: dict[str, BaseTool] = {
        "get_quote": GetQuoteTool(market),
        "get_history": GetHistoryTool(market),
        "get_indicators": GetIndicatorsTool(market),
        "get_news": GetNewsTool(market),
    }
    if memory_store is not None and embeddings is not None:
        from investia.memory.tools import RecallMemoryTool, SaveMemoryTool

        tools["save_memory"] = SaveMemoryTool(memory_store, embeddings)
        tools["recall_memory"] = RecallMemoryTool(memory_store, embeddings)
    if portfolio_service is not None:
        tools["get_portfolio"] = GetPortfolioTool(portfolio_service)
        tools["simulate_order"] = SimulateOrderTool(portfolio_service)
    return tools
