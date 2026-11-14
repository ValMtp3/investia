"""Tests 16a — mémoire temporelle : dédup à l'écriture, supersede, soft delete,
recall courant vs historique, nouveaux outils update_memory / forget_memory."""

import math
from datetime import UTC, datetime

import pytest
from test_memory import FakeEmbeddings
from test_sse import FakeMarket

from investia.memory.store import SaveResult
from investia.memory.tools import (
    ForgetMemoryTool,
    RecallMemoryTool,
    SaveMemoryTool,
    UpdateMemoryTool,
)
from investia.tools import build_tools
from investia.tools.base import ToolError


class FakeTemporalMemoryStore:
    """Store mémoire temporel in-memory, conforme au nouveau protocol."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self._next = 0

    async def save(
        self,
        content: str,
        embedding: list[float] | None = None,
        *,
        provenance: str = "agent",
        scope: str = "global",
        dedup_threshold: float = 0.97,
    ) -> SaveResult:
        vector = embedding or (await FakeEmbeddings().embed([content]))[0]
        for row in self.rows.values():
            if (
                row["valid_until"] is None
                and _cos(vector, row["embedding"]) >= dedup_threshold
            ):
                return SaveResult(id=row["id"], duplicate=True)
        self._next += 1
        memory_id = f"mem-{self._next}"
        self.rows[memory_id] = {
            "id": memory_id,
            "content": content,
            "embedding": vector,
            "provenance": provenance,
            "scope": scope,
            "valid_from": datetime.now(UTC),
            "valid_until": None,
            "superseded_by": None,
        }
        return SaveResult(id=memory_id, duplicate=False)

    async def supersede(
        self,
        old_id: str,
        new_content: str,
        embedding: list[float] | None = None,
        *,
        provenance: str = "agent",
        scope: str = "global",
    ) -> str:
        old = self.rows.get(old_id)
        if old is None or old["valid_until"] is not None:
            raise ValueError(f"souvenir inconnu ou archivé: {old_id}")
        result = await self.save(
            new_content, embedding, provenance=provenance, scope=scope
        )
        if result.duplicate:
            raise ValueError(f"contenu identique déjà présent: {old_id}")
        now = datetime.now(UTC)
        old["valid_until"] = now
        old["superseded_by"] = result.id
        return result.id

    async def forget(self, memory_id: str) -> bool:
        row = self.rows.get(memory_id)
        if row is None or row["valid_until"] is not None:
            return False
        row["valid_until"] = datetime.now(UTC)
        return True

    async def recall(
        self, query: str, k: int = 5, *, include_history: bool = False
    ) -> list[dict]:
        query_vector = (await FakeEmbeddings().embed([query]))[0]
        scored = []
        for row in self.rows.values():
            if row["valid_until"] is not None and not include_history:
                continue
            scored.append((_cos(query_vector, row["embedding"]), row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [_public(row, score) for score, row in scored[:k]]

    async def history(self, memory_id: str) -> list[dict]:
        if memory_id not in self.rows:
            return []
        # Remonter à l'ancêtre le plus ancien, puis redescendre (récente d'abord).
        current = memory_id
        while any(r["superseded_by"] == current for r in self.rows.values()):
            current = next(
                rid for rid, r in self.rows.items() if r["superseded_by"] == current
            )
        chain = []
        while current is not None:
            chain.append(_public(self.rows[current], None))
            current = self.rows[current]["superseded_by"]
        chain.reverse()  # la plus récente d'abord
        return chain


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def _public(row, score):
    return {
        "id": row["id"],
        "content": row["content"],
        "score": score,
        "provenance": row["provenance"],
        "scope": row["scope"],
        "valid_from": row["valid_from"].isoformat(),
        "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
    }


@pytest.fixture
def store():
    return FakeTemporalMemoryStore()


@pytest.fixture
def embeddings():
    return FakeEmbeddings()


# --- save : dédup sémantique à l'écriture ------------------------------------


async def test_save_returns_save_result_and_dedups_identical_content(store):
    first = await store.save("profil de risque prudent")
    assert isinstance(first, SaveResult)
    assert first.duplicate is False
    second = await store.save("profil de risque prudent")
    assert second.duplicate is True
    assert second.id == first.id  # idempotent : même id, rien de réinséré
    assert len(store.rows) == 1


async def test_save_different_content_creates_new_memory(store):
    a = await store.save("profil de risque prudent")
    b = await store.save("horizon d'investissement 10 ans")
    assert a.id != b.id
    assert b.duplicate is False
    assert len(store.rows) == 2


async def test_save_memory_tool_exposes_duplicate_and_provenance(store, embeddings):
    tool = SaveMemoryTool(store=store, embeddings=embeddings)
    result = await tool.run(
        tool.args_schema(content="profil prudent", provenance="user", scope="risk")
    )
    assert result["saved"] is True
    assert result["duplicate"] is False
    assert store.rows[result["id"]]["provenance"] == "user"
    assert store.rows[result["id"]]["scope"] == "risk"
    again = await tool.run(tool.args_schema(content="profil prudent"))
    assert again["duplicate"] is True


# --- supersede : remplacement versionné --------------------------------------


async def test_supersede_archives_old_and_keeps_history(store):
    old = await store.save("profil de risque prudent")
    new_id = await store.supersede(old.id, "profil de risque modéré")
    assert new_id != old.id
    old_row = store.rows[old.id]
    assert old_row["valid_until"] is not None  # archivé, pas supprimé
    assert old_row["superseded_by"] == new_id

    recalled = await store.recall("profil de risque")
    assert [r["content"] for r in recalled] == ["profil de risque modéré"]
    assert recalled[0]["valid_until"] is None

    hist = await store.history(new_id)
    assert [h["content"] for h in hist] == [
        "profil de risque modéré",
        "profil de risque prudent",
    ]


async def test_supersede_unknown_or_archived_id_raises(store):
    with pytest.raises(ValueError):
        await store.supersede("mem-999", "nouveau contenu")
    old = await store.save("profil prudent")
    await store.supersede(old.id, "profil modéré")
    with pytest.raises(ValueError):
        await store.supersede(old.id, "encore autre chose")  # déjà archivé


async def test_update_memory_tool_maps_value_error_to_tool_error(store, embeddings):
    tool = UpdateMemoryTool(store=store, embeddings=embeddings)
    with pytest.raises(ToolError):
        await tool.run(tool.args_schema(memory_id="mem-999", content="x"))
    old = await store.save("profil prudent")
    result = await tool.run(tool.args_schema(memory_id=old.id, content="profil modéré"))
    assert result["updated"] is True
    assert result["superseded"] == old.id
    assert result["id"] != old.id


# --- forget : soft delete -----------------------------------------------------


async def test_forget_is_soft_delete_and_recall_skips_archived_by_default(store):
    mem = await store.save("il déteste les cryptos")
    assert await store.forget(mem.id) is True
    assert store.rows[mem.id]["valid_until"] is not None  # toujours en base
    assert await store.recall("cryptos") == []
    with_history = await store.recall("cryptos", include_history=True)
    assert len(with_history) == 1
    assert with_history[0]["valid_until"] is not None
    assert await store.forget(mem.id) is False  # déjà archivé
    assert await store.forget("mem-999") is False


async def test_forget_memory_tool(store, embeddings):
    tool = ForgetMemoryTool(store=store, embeddings=embeddings)
    mem = await store.save("il déteste les cryptos")
    result = await tool.run(tool.args_schema(memory_id=mem.id))
    assert result["forgotten"] is True
    again = await tool.run(tool.args_schema(memory_id=mem.id))
    assert again["forgotten"] is False


# --- recall : champs temporels exposés ---------------------------------------


async def test_recall_exposes_temporal_fields(store):
    await store.save("horizon 10 ans", provenance="user", scope="goals")
    recalled = await store.recall("horizon", k=1)
    row = recalled[0]
    assert row["id"].startswith("mem-")
    assert row["provenance"] == "user"
    assert row["scope"] == "goals"
    assert row["valid_from"]
    assert row["valid_until"] is None


async def test_recall_memory_tool_has_include_history_arg(store, embeddings):
    tool = RecallMemoryTool(store=store, embeddings=embeddings)
    mem = await store.save("il déteste les cryptos")
    await store.forget(mem.id)
    current = await tool.run(tool.args_schema(query="cryptos"))
    assert current["count"] == 0
    full = await tool.run(tool.args_schema(query="cryptos", include_history=True))
    assert full["count"] == 1


# --- câblage build_tools ------------------------------------------------------


def test_build_tools_wires_four_memory_tools_when_store_provided(store, embeddings):
    tools = build_tools(FakeMarket(), memory_store=store, embeddings=embeddings)
    for name in ("save_memory", "recall_memory", "update_memory", "forget_memory"):
        assert name in tools


def test_build_tools_without_memory_stays_unchanged(embeddings):
    tools = build_tools(FakeMarket())
    assert not any("memory" in name for name in tools)


def test_memory_tools_expose_llm_contract(store, embeddings):
    for tool in (
        SaveMemoryTool(store, embeddings),
        RecallMemoryTool(store, embeddings),
        UpdateMemoryTool(store, embeddings),
        ForgetMemoryTool(store, embeddings),
    ):
        spec = tool.to_openai_tool()
        assert spec["function"]["parameters"]["type"] == "object"
    names = {
        t.to_openai_tool()["function"]["name"]
        for t in (
            SaveMemoryTool(store, embeddings),
            RecallMemoryTool(store, embeddings),
            UpdateMemoryTool(store, embeddings),
            ForgetMemoryTool(store, embeddings),
        )
    }
    assert names == {"save_memory", "recall_memory", "update_memory", "forget_memory"}
