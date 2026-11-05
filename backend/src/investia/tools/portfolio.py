"""Outil get_portfolio : l'état du portefeuille simulé pour l'agent (étape 4.6)."""

import logging
from typing import Any, Protocol

from pydantic import BaseModel

from investia.tools.base import BaseTool, ToolError

logger = logging.getLogger(__name__)


class PortfolioReader(Protocol):
    """Ce dont l'outil a besoin : lire l'état du portefeuille (lecture seule)."""

    async def get_portfolio(self) -> dict[str, Any]: ...


class NoArgs(BaseModel):
    """Outil sans argument : le portefeuille par défaut est unique."""


class GetPortfolioTool(BaseTool[NoArgs]):
    name = "get_portfolio"
    description = (
        "État du portefeuille simulé : cash, positions (quantité, prix moyen, prix "
        "actuel avec source et horodatage, valeur) et valeur totale, en EUR. "
        "Lecture seule, aucun ordre n'est passé."
    )
    args_schema = NoArgs

    def __init__(self, portfolio_service: PortfolioReader) -> None:
        self._portfolio_service = portfolio_service

    async def run(self, args: NoArgs) -> dict[str, Any]:
        try:
            return await self._portfolio_service.get_portfolio()
        except Exception as error:
            # Le détail (DB, réseau…) reste côté serveur : le LLM et les traces
            # ne reçoivent qu'un message générique.
            logger.exception("get_portfolio: erreur interne du service portefeuille")
            raise ToolError(
                self.name, "erreur interne lors de la lecture du portefeuille"
            ) from error
