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
