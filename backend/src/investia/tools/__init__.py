"""Registre des outils exposés à la boucle d'agent."""

from investia.market.base import MarketDataService
from investia.tools.base import BaseTool
from investia.tools.history import GetHistoryTool
from investia.tools.indicators import GetIndicatorsTool
from investia.tools.news import GetNewsTool
from investia.tools.quote import GetQuoteTool

__all__ = ["BaseTool", "build_tools"]


def build_tools(
    market: MarketDataService,
    memory_store=None,
    embeddings=None,
) -> dict[str, BaseTool]:
    """Les 4 outils marché, + save_memory/recall_memory si une mémoire est dispo."""
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
    return tools
