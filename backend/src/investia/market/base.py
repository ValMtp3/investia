"""Format commun des données de marché et interface des connecteurs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class MarketDataError(Exception):
    """Erreur d'un fournisseur de données — nomme toujours la source."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source


@dataclass(frozen=True)
class MarketData:
    """Une donnée de marché, toujours avec sa source et son horodatage."""

    value: float
    currency: str
    source: str
    timestamp: datetime
    delayed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "currency": self.currency,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "delayed": self.delayed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketData":
        return cls(
            value=float(data["value"]),
            currency=data["currency"],
            source=data["source"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            delayed=bool(data.get("delayed", False)),
        )


class MarketDataConnector(Protocol):
    """Interface commune : un connecteur par source de données."""

    name: str

    async def get_quote(self, symbol: str) -> MarketData:
        """Prix actuel (ou dernier connu) d'un symbole."""
        ...

    async def get_history(self, symbol: str, days: int = 30) -> list[MarketData]:
        """Historique des cours de clôture, un point par jour."""
        ...

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        """Actualités récentes sur un symbole."""
        ...
