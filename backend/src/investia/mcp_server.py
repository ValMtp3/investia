"""Serveur MCP Investia (étape 5.2, D58) : expose les outils du harness comme
serveur MCP (FastMCP), servi en streamable HTTP sur /mcp derrière Authelia.

Les schémas exposés sont générés par FastMCP depuis les annotations des wrappers ;
chaque appel est re-validé par le schéma Pydantic interne de l'outil (args_schema),
puis exécuté. Les erreurs internes ne fuient pas au client MCP (message générique,
détail loggué côté serveur).
"""

import logging
from typing import Any, Literal

from fastmcp import Context, FastMCP
from mcp.types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult
from pydantic import BaseModel

from investia.agent.approval import payload_hash_for
from investia.market.base import MarketDataService
from investia.tools import build_tools
from investia.tools.base import BaseTool
from investia.tools.portfolio import PortfolioServiceLike

logger = logging.getLogger(__name__)


class OrderConfirmation(BaseModel):
    """Schéma d'elicitation (MRTR, form mode) pour confirmer un ordre simulé (15a)."""

    confirm: bool
    note: str = ""


# Clé de la demande d'input dans le InputRequiredResult (SEP-2322).
CONFIRM_KEY = "order_confirmation"


async def _run_tool(tool: BaseTool, arguments: dict[str, Any]) -> dict[str, Any]:
    """Valide avec le schéma interne, exécute, et masque toute erreur interne."""
    args = tool.args_schema.model_validate(arguments)
    try:
        return await tool.run(args)
    except Exception as error:
        # Le détail (DB, réseau, clé…) reste côté serveur.
        logger.exception("MCP tool %s: erreur interne", tool.name)
        raise ValueError(f"{tool.name}: erreur interne lors de l'exécution") from error


def build_mcp_server(
    market: MarketDataService, portfolio_service: PortfolioServiceLike
) -> FastMCP:
    """Construit le serveur MCP avec les 6 outils Investia."""
    mcp = FastMCP("investia")
    tools = build_tools(market, portfolio_service=portfolio_service)

    quote = tools["get_quote"]

    @mcp.tool(name=quote.name, description=quote.description)
    async def get_quote(symbol: str) -> dict[str, Any]:
        return await _run_tool(quote, {"symbol": symbol})

    history = tools["get_history"]

    @mcp.tool(name=history.name, description=history.description)
    async def get_history(symbol: str, days: int = 30) -> dict[str, Any]:
        return await _run_tool(history, {"symbol": symbol, "days": days})

    indicators = tools["get_indicators"]

    @mcp.tool(name=indicators.name, description=indicators.description)
    async def get_indicators(symbol: str, days: int = 60) -> dict[str, Any]:
        return await _run_tool(indicators, {"symbol": symbol, "days": days})

    news = tools["get_news"]

    @mcp.tool(name=news.name, description=news.description)
    async def get_news(symbol: str, limit: int = 5) -> dict[str, Any]:
        return await _run_tool(news, {"symbol": symbol, "limit": limit})

    portfolio = tools["get_portfolio"]

    @mcp.tool(name=portfolio.name, description=portfolio.description)
    async def get_portfolio() -> dict[str, Any]:
        return await _run_tool(portfolio, {})

    order = tools["simulate_order"]

    @mcp.tool(name=order.name, description=order.description)
    async def simulate_order(
        symbol: str, side: Literal["buy", "sell"], quantity: float, ctx: Context
    ) -> dict[str, Any] | InputRequiredResult:
        # 15a : confirmation humaine par MRTR (SEP-2322, spec MCP 2026-07-28) —
        # deny-by-default : aucun ordre sans accept explicite. Le request_state
        # embarque le hash du payload (13d) pour lier la confirmation à l'ordre.
        payload_hash = payload_hash_for(symbol, side, quantity)
        responses = ctx.input_responses
        if responses is None:
            # Premier passage : on demande la confirmation (résultat input_required).
            return InputRequiredResult(
                input_requests={
                    CONFIRM_KEY: ElicitRequest(
                        method="elicitation/create",
                        params=ElicitRequestFormParams(
                            mode="form",
                            message=(
                                f"Confirmer l'ordre simulé : "
                                f"{side} {quantity} {symbol} ?"
                            ),
                            requested_schema=OrderConfirmation.model_json_schema(),
                        ),
                    )
                },
                request_state=payload_hash,
            )
        elicit_result = responses.get(CONFIRM_KEY)
        content = getattr(elicit_result, "content", None)
        confirm = isinstance(content, dict) and bool(content.get("confirm"))
        if (
            getattr(elicit_result, "action", None) != "accept"
            or not confirm
            or ctx.request_state != payload_hash
        ):
            raise ValueError("simulate_order: ordre non confirmé — aucun ordre exécuté")
        return await _run_tool(
            order, {"symbol": symbol, "side": side, "quantity": quantity}
        )

    return mcp
