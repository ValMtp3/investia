"""Outils mémoire exposés à l'agent : save_memory / recall_memory."""

from typing import Any

from pydantic import BaseModel, Field

from investia.memory.embeddings import Embeddings
from investia.memory.store import MemoryStoreProtocol
from investia.tools.base import BaseTool, ToolError


class SaveMemoryArgs(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class SaveMemoryTool(BaseTool[SaveMemoryArgs]):
    name = "save_memory"
    description = (
        "Enregistre un fait durable sur l'utilisateur (profil de risque, préférences, "
        "contraintes) dans la mémoire longue."
    )
    args_schema = SaveMemoryArgs

    def __init__(self, store: MemoryStoreProtocol, embeddings: Embeddings) -> None:
        self._store = store
        self._embeddings = embeddings

    async def run(self, args: SaveMemoryArgs) -> dict[str, Any]:
        try:
            memory_id = await self._store.save(args.content.strip(), None)
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {"saved": True, "id": memory_id}


class RecallMemoryArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    k: int = Field(5, ge=1, le=20)


class RecallMemoryTool(BaseTool[RecallMemoryArgs]):
    name = "recall_memory"
    description = (
        "Retrouve les souvenirs pertinents de la mémoire longue par recherche "
        "sémantique (pas par mot-clé exact)."
    )
    args_schema = RecallMemoryArgs

    def __init__(self, store: MemoryStoreProtocol, embeddings: Embeddings) -> None:
        self._store = store
        self._embeddings = embeddings

    async def run(self, args: RecallMemoryArgs) -> dict[str, Any]:
        try:
            memories = await self._store.recall(args.query.strip(), k=args.k)
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {"count": len(memories), "memories": memories}
