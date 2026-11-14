"""Client d'embeddings via OpenRouter (text-embedding-3-small, 1536 dims).

Mockable : passer `http_client` avec un MockTransport en test.
"""

import hashlib
from typing import Protocol

import httpx
from pydantic import SecretStr

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIM = 1536


class Embeddings(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenRouterEmbeddings:
    def __init__(
        self,
        base_url: str,
        api_key: SecretStr,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            f"{self._base_url}/embeddings",
            json={"model": EMBEDDING_MODEL, "input": texts},
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
        )
        if response.status_code != 200:
            raise EmbeddingsError(f"HTTP {response.status_code} sur /embeddings")
        data = response.json()
        vectors = [item["embedding"] for item in data["data"]]
        if any(len(v) != EMBEDDING_DIM for v in vectors):
            raise EmbeddingsError(f"dimension inattendue (attendu {EMBEDDING_DIM})")
        return vectors


class EmbeddingsError(Exception):
    pass


# Modèle local par défaut (16b) : Qwen3-Embedding-0.6B, licence Apache-2.0.
DEFAULT_LOCAL_EMBEDDING_MODEL = "Qwen3-Embedding-0.6B"


def pad_to_dim(vector: list[float], dim: int = EMBEDDING_DIM) -> list[float]:
    """Complète un vecteur par des zéros jusqu'à `dim` (tronque si plus long).

    Pour la similarité cosinus, ajouter des zéros est exact : ni le produit
    scalaire ni la norme ne changent, donc cos(a, b) est identique avec ou
    sans padding. Ça permet de garder la colonne pgvector en vector(1536)
    sans migration.
    """
    if len(vector) >= dim:
        return list(vector[:dim])
    return list(vector) + [0.0] * (dim - len(vector))


class LocalEmbeddings:
    """Embeddings 100 % locaux via sentence-transformers (16b).

    Le modèle est chargé une fois (téléchargement HF au premier usage, puis
    cache local). L'encodage est bloquant -> exécuté dans un thread à part.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL,
        device: str = "cpu",
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise EmbeddingsError(
                "sentence-transformers n'est pas installé : "
                "`uv add sentence-transformers` ou EMBEDDINGS_BACKEND=openrouter"
            ) from error
        self._model = SentenceTransformer(model_name, device=device)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(None, self._encode, texts)
        return [pad_to_dim([float(v) for v in vector]) for vector in vectors]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class FakeEmbeddingsForTests:
    """Embeddings déterministes pour les tests d'intégration (hash du texte)."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [b / 255.0 for b in digest[:8]]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec] + [0.0] * (EMBEDDING_DIM - 8))
        return vectors
