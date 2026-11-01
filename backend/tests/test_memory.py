"""Tests unitaires de la mémoire (embeddings mockés, store fake)."""

import httpx
import pytest
from pydantic import SecretStr

from investia.memory.embeddings import OpenRouterEmbeddings
from investia.memory.tools import RecallMemoryTool, SaveMemoryTool


class FakeEmbeddings:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        # vecteur déterministe : hash du texte normalisé
        import hashlib

        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [b / 255.0 for b in digest[:8]]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec] + [0.0] * 1528)
        return vectors


class FakeMemoryStore:
    def __init__(self):
        self.memories = {}

    async def save(self, content: str, embedding: list[float] | None) -> str:
        if embedding is None:
            embedding = (await FakeEmbeddings().embed([content]))[0]
        memory_id = f"mem-{len(self.memories) + 1}"
        self.memories[memory_id] = {"content": content, "embedding": embedding}
        return memory_id

    async def recall(self, query: str, k: int = 5) -> list[dict]:
        import math

        query_embedding = (await FakeEmbeddings().embed([query]))[0]

        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return dot / (na * nb)

        scored = [
            (cos(query_embedding, m["embedding"]), m["content"])
            for m in self.memories.values()
        ]
        scored.sort(reverse=True)
        return [{"content": c, "score": s} for s, c in scored[:k]]


def make_embeddings(handler) -> OpenRouterEmbeddings:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenRouterEmbeddings(
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr("or-test"),
        http_client=http,
    )


async def test_embeddings_client_calls_openrouter_and_returns_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        assert request.headers["Authorization"] == "Bearer or-test"
        return httpx.Response(200, json={"data": [{"embedding": [0.1] * 1536}]})

    client = make_embeddings(handler)
    vectors = await client.embed(["bonjour"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 1536
    assert vectors[0][0] == pytest.approx(0.1)


async def test_save_and_recall_tools_use_the_store():
    store = FakeMemoryStore()
    embeddings = FakeEmbeddings()
    save_tool = SaveMemoryTool(store=store, embeddings=embeddings)
    recall_tool = RecallMemoryTool(store=store, embeddings=embeddings)

    result = await save_tool.run(
        save_tool.args_schema(content="Je préfère un profil de risque prudent")
    )
    assert result["saved"] is True
    assert "mem-1" in result["id"]

    recall = await recall_tool.run(
        recall_tool.args_schema(query="mon profil de risque")
    )
    assert recall["count"] == 1
    assert "prudent" in recall["memories"][0]["content"]


def test_memory_tools_expose_llm_contract():
    store = FakeMemoryStore()
    embeddings = FakeEmbeddings()
    for tool in (
        SaveMemoryTool(store, embeddings),
        RecallMemoryTool(store, embeddings),
    ):
        spec = tool.to_openai_tool()
        assert spec["function"]["name"] in ("save_memory", "recall_memory")
        assert spec["function"]["parameters"]["type"] == "object"
