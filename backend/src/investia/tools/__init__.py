"""Registre des outils exposés à la boucle d'agent."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from investia.market.forecast import Forecaster

from investia.market.base import MarketDataService
from investia.tools.base import BaseTool
from investia.tools.history import GetHistoryTool
from investia.tools.indicators import GetIndicatorsTool
from investia.tools.news import GetNewsTool
from investia.tools.order import SimulateOrderTool
from investia.tools.pdf import PdfReader, ReadPdfTool
from investia.tools.portfolio import GetPortfolioTool, PortfolioServiceLike
from investia.tools.python_sandbox import PythonSandbox, RunPythonTool
from investia.tools.quote import GetQuoteTool
from investia.tools.web_search import WebSearcher, WebSearchTool

__all__ = ["BaseTool", "build_tools"]


def build_tools(
    market: MarketDataService,
    memory_store=None,
    embeddings=None,
    portfolio_service: PortfolioServiceLike | None = None,
    web_searcher: WebSearcher | None = None,
    pdf_reader: PdfReader | None = None,
    python_sandbox: PythonSandbox | None = None,
    forecaster: "Forecaster | None" = None,
) -> dict[str, BaseTool]:
    """Les 4 outils marché, + mémoire si dispo, + portefeuille si service fourni,
    + web_search / read_pdf / run_python si les services sont fournis
    (rétrocompatible)."""
    tools: dict[str, BaseTool] = {
        "get_quote": GetQuoteTool(market),
        "get_history": GetHistoryTool(market),
        "get_indicators": GetIndicatorsTool(market),
        "get_news": GetNewsTool(market),
    }
    if memory_store is not None and embeddings is not None:
        from investia.memory.tools import (
            ForgetMemoryTool,
            RecallMemoryTool,
            SaveMemoryTool,
            UpdateMemoryTool,
        )

        tools["save_memory"] = SaveMemoryTool(memory_store, embeddings)
        tools["recall_memory"] = RecallMemoryTool(memory_store, embeddings)
        tools["update_memory"] = UpdateMemoryTool(memory_store, embeddings)
        tools["forget_memory"] = ForgetMemoryTool(memory_store, embeddings)
    if portfolio_service is not None:
        tools["get_portfolio"] = GetPortfolioTool(portfolio_service)
        tools["simulate_order"] = SimulateOrderTool(portfolio_service)
    if web_searcher is not None:
        tools["web_search"] = WebSearchTool(web_searcher)
    if pdf_reader is not None:
        tools["read_pdf"] = ReadPdfTool(pdf_reader)
    if python_sandbox is not None:
        tools["run_python"] = RunPythonTool(python_sandbox)
    if forecaster is not None:
        from investia.tools.forecast import GetForecastTool

        tools["get_forecast"] = GetForecastTool(market, forecaster)
    return tools
