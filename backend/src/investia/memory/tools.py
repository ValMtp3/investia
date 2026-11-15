"""Outils mémoire exposés à l'agent : save / recall / update / forget (16a)."""

from typing import Any

from pydantic import BaseModel, Field

from investia.memory.embeddings import Embeddings
from investia.memory.store import MemoryStoreProtocol
from investia.tools.base import BaseTool, ToolError


class SaveMemoryArgs(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    provenance: str = Field("agent", min_length=1, max_length=50)
    scope: str = Field("global", min_length=1, max_length=50)


class SaveMemoryTool(BaseTool[SaveMemoryArgs]):
    name = "save_memory"
    description = (
        "Enregistre un fait durable sur l'utilisateur (profil de risque, préférences, "
        "contraintes) dans la mémoire longue. Un contenu quasi identique à un souvenir "
        "déjà actif n'est pas réinséré (retourne duplicate=true avec l'id existant)."
    )
    args_schema = SaveMemoryArgs

    def __init__(self, store: MemoryStoreProtocol, embeddings: Embeddings) -> None:
        self._store = store
        self._embeddings = embeddings

    async def run(self, args: SaveMemoryArgs) -> dict[str, Any]:
        try:
            result = await self._store.save(
                args.content.strip(),
                None,
                provenance=args.provenance,
                scope=args.scope,
            )
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {"saved": True, "id": result.id, "duplicate": result.duplicate}


class RecallMemoryArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    k: int = Field(5, ge=1, le=20)
    include_history: bool = Field(
        False,
        description="Inclure aussi les souvenirs archivés (valid_until renseigné).",
    )


class RecallMemoryTool(BaseTool[RecallMemoryArgs]):
    name = "recall_memory"
    description = (
        "Retrouve les souvenirs pertinents de la mémoire longue par recherche "
        "sémantique (pas par mot-clé exact). Par défaut, seuls les souvenirs "
        "encore valides sont retournés."
    )
    args_schema = RecallMemoryArgs

    def __init__(self, store: MemoryStoreProtocol, embeddings: Embeddings) -> None:
        self._store = store
        self._embeddings = embeddings

    async def run(self, args: RecallMemoryArgs) -> dict[str, Any]:
        try:
            memories = await self._store.recall(
                args.query.strip(), k=args.k, include_history=args.include_history
            )
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {"count": len(memories), "memories": memories}


class UpdateMemoryArgs(BaseModel):
    memory_id: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1, max_length=2000)
    provenance: str = Field("agent", min_length=1, max_length=50)
    scope: str = Field("global", min_length=1, max_length=50)


class UpdateMemoryTool(BaseTool[UpdateMemoryArgs]):
    name = "update_memory"
    description = (
        "Remplace un souvenir actif par une version corrigée : l'ancien est archivé "
        "(valid_until + superseded_by, jamais supprimé) et le nouveau devient actif."
    )
    args_schema = UpdateMemoryArgs

    def __init__(self, store: MemoryStoreProtocol, embeddings: Embeddings) -> None:
        self._store = store
        self._embeddings = embeddings

    async def run(self, args: UpdateMemoryArgs) -> dict[str, Any]:
        try:
            new_id = await self._store.supersede(
                args.memory_id,
                args.content.strip(),
                None,
                provenance=args.provenance,
                scope=args.scope,
            )
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {"updated": True, "id": new_id, "superseded": args.memory_id}


class ForgetMemoryArgs(BaseModel):
    memory_id: str = Field(..., min_length=1, max_length=64)
    # 23e : hard=True -> purge RGPD (suppression réelle + audit), défaut soft.
    hard: bool = False
    reason: str = Field(default="", max_length=500)


class ForgetMemoryTool(BaseTool[ForgetMemoryArgs]):
    name = "forget_memory"
    description = (
        "Oublie un souvenir actif (soft delete par défaut : il reste en base "
        "archivé, il n'est plus retourné par recall_memory). Avec hard=true : "
        "suppression réelle RGPD, la ligne est supprimée et un audit redacted "
        "est conservé (demander un `reason`)."
    )
    args_schema = ForgetMemoryArgs

    def __init__(self, store: MemoryStoreProtocol, embeddings: Embeddings) -> None:
        self._store = store
        self._embeddings = embeddings

    async def run(self, args: ForgetMemoryArgs) -> dict[str, Any]:
        try:
            if args.hard:
                purged = await self._store.purge(args.memory_id, args.reason)
                return {"purged": purged}
            forgotten = await self._store.forget(args.memory_id)
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {"forgotten": forgotten}
