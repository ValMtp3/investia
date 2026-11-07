"""Package memory : mémoire longue pgvector + outils agent."""

from investia.config import Settings
from investia.db import get_session
from investia.memory.embeddings import Embeddings, OpenRouterEmbeddings
from investia.memory.store import DbMemoryStore, MemoryStoreProtocol
from investia.memory.tools import RecallMemoryTool, SaveMemoryTool

__all__ = [
    "DbMemoryStore",
    "Embeddings",
    "MemoryStoreProtocol",
    "OpenRouterEmbeddings",
    "RecallMemoryTool",
    "SaveMemoryTool",
    "build_memory",
]


def build_memory(settings: Settings) -> tuple[DbMemoryStore, OpenRouterEmbeddings]:
    embeddings = OpenRouterEmbeddings(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key or _missing_key(),
    )
    return DbMemoryStore(get_session(), embeddings), embeddings


def _missing_key():
    raise RuntimeError("OPENROUTER_API_KEY manquante (requis pour les embeddings)")
