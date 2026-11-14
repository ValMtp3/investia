"""Package memory : mémoire longue pgvector + outils agent."""

import logging

from investia.config import Settings
from investia.db import get_session
from investia.memory.embeddings import (
    Embeddings,
    EmbeddingsError,
    LocalEmbeddings,
    OpenRouterEmbeddings,
)
from investia.memory.store import (
    DbMemoryStore,
    MemoryStoreProtocol,
    SaveResult,
)
from investia.memory.tools import (
    ForgetMemoryTool,
    RecallMemoryTool,
    SaveMemoryTool,
    UpdateMemoryTool,
)

__all__ = [
    "DbMemoryStore",
    "Embeddings",
    "LocalEmbeddings",
    "MemoryStoreProtocol",
    "OpenRouterEmbeddings",
    "ForgetMemoryTool",
    "RecallMemoryTool",
    "SaveMemoryTool",
    "SaveResult",
    "UpdateMemoryTool",
    "build_memory",
]


logger = logging.getLogger(__name__)


def build_memory(settings: Settings) -> tuple[DbMemoryStore, Embeddings]:
    """Construit le store mémoire + le backend d'embeddings (16b).

    backend=local : embeddings 100 % locaux (sentence-transformers), avec
    fallback sur OpenRouter + warning si le local est indisponible.
    """
    embeddings: Embeddings
    if settings.embeddings_backend == "local":
        try:
            embeddings = LocalEmbeddings(model_name=settings.local_embedding_model)
        except EmbeddingsError as error:
            logger.warning(
                "embeddings locaux indisponibles (%s), fallback OpenRouter", error
            )
            embeddings = _openrouter_embeddings(settings)
    else:
        embeddings = _openrouter_embeddings(settings)
    return DbMemoryStore(get_session(), embeddings), embeddings


def _openrouter_embeddings(settings: Settings) -> OpenRouterEmbeddings:
    return OpenRouterEmbeddings(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key or _missing_key(),
    )


def _missing_key():
    raise RuntimeError("OPENROUTER_API_KEY manquante (requis pour les embeddings)")
