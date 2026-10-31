"""Base des outils exposés à l'agent LLM (function calling, étape 1.4)."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SymbolArgs(BaseModel):
    """Schéma commun : un symbole non vide (espaces retirés)."""

    symbol: str = Field(..., min_length=1, max_length=20)

    @field_validator("symbol")
    @classmethod
    def symbol_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbole vide")
        return value


class ToolError(Exception):
    """Erreur d'exécution d'un outil — nomme l'outil et la cause."""

    def __init__(self, tool: str, detail: str) -> None:
        super().__init__(f"{tool}: {detail}")
        self.tool = tool


class BaseTool[T: BaseModel](ABC):
    """Un outil = name + description (pour le LLM) + schéma d'entrée + run()."""

    name: str
    description: str
    args_schema: type[T]

    @abstractmethod
    async def run(self, args: T) -> dict[str, Any]:
        """Exécute l'outil avec des arguments déjà validés."""
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        """Format function-calling OpenAI, consommé par la boucle d'agent."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_schema.model_json_schema(),
            },
        }
