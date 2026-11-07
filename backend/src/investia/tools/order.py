"""Outil simulate_order : ordre SIMULÉ de l'agent (étape 5.1).

Dans la boucle avec validation humaine (D57), l'appel est intercepté avant
exécution : l'agent s'arrête, demande l'accord, et l'ordre n'est exécuté que
si la décision est « approved ». Hors boucle (serveur MCP, 5.2), run() exécute
directement l'ordre — toujours simulé, jamais réel.
"""

import logging
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from investia.tools.base import BaseTool, ToolError

logger = logging.getLogger(__name__)


class PortfolioWriter(Protocol):
    """Ce dont l'outil a besoin : passer un ordre simulé."""

    async def place_order(
        self, symbol: str, side: str, quantity: float
    ) -> dict[str, Any]: ...


class OrderArgs(BaseModel):
    """Ordre simulé : symbole, sens, quantité strictement positive."""

    symbol: str = Field(..., min_length=1, max_length=20)
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)

    @field_validator("symbol")
    @classmethod
    def symbol_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbole vide")
        return value


class SimulateOrderTool(BaseTool[OrderArgs]):
    name = "simulate_order"
    description = (
        "Passe un ordre SIMULÉ (jamais réel) sur le portefeuille fictif : symbole, "
        "sens (buy/sell) et quantité. Dans le dashboard, cet appel déclenche une "
        "demande de validation humaine : l'ordre n'est exécuté que si l'utilisateur "
        "clique « Valider ». Aucun ordre sans accord."
    )
    args_schema = OrderArgs

    def __init__(self, portfolio_service: PortfolioWriter) -> None:
        self._portfolio_service = portfolio_service

    async def run(self, args: OrderArgs) -> dict[str, Any]:
        try:
            return await self._portfolio_service.place_order(
                args.symbol.strip().upper(), args.side, args.quantity
            )
        except Exception as error:
            # Le détail (DB, marché…) reste côté serveur : le LLM et les traces
            # ne reçoivent qu'un message générique.
            logger.exception("simulate_order: erreur interne du service portefeuille")
            raise ToolError(
                self.name, "erreur interne lors du passage de l'ordre simulé"
            ) from error
