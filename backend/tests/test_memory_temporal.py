"""Tests 16a — mémoire temporelle : dédup à l'écriture, supersede, soft delete,
recall courant vs historique, nouveaux outils update_memory / forget_memory."""

import math
from datetime import UTC, datetime

import pytest
from test_memory import FakeEmbeddings
from test_sse import FakeMarket

from investia.memory.store import (
    DEDUP_THRESHOLD,
    SUPERSEDE_THRESHOLD,
    SaveResult,
    dedup_action,
    scrub_content,
)
from investia.memory.tools import (
    ForgetMemoryArgs,
    ForgetMemoryTool,
    RecallMemoryTool,
    SaveMemoryTool,
    UpdateMemoryTool,
)
from investia.redaction import REDACTED, RegexRedactor
from investia.tools import build_tools
from investia.tools.base import ToolError


class FakeTemporalMemoryStore:
    """Store mémoire temporel in-memory, conforme au nouveau protocol."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.audit: list[dict] = []  # 23e : memory_purge_audit
        self._next = 0

    async def save(
        self,
        content: str,
        embedding: list[float] | None = None,
        *,
        provenance: str = "agent",
        scope: str = "global",
        dedup_threshold: float = DEDUP_THRESHOLD,
        supersede_threshold: float = SUPERSEDE_THRESHOLD,
    ) -> SaveResult:
        # 23e : scrub avant embedding + stockage, comme DbMemoryStore.
        content, redacted = scrub_content(content)
        vector = embedding or (await FakeEmbeddings().embed([content]))[0]
        # Voisin le plus proche parmi les souvenirs courants.
        nearest_id: str | None = None
        nearest_score = -1.0
        for row in self.rows.values():
            if row["valid_until"] is not None:
                continue
            score = _cos(vector, row["embedding"])
            if score > nearest_score:
                nearest_score = score
                nearest_id = row["id"]
        superseded: str | None = None
        if nearest_id is not None:
            action = dedup_action(nearest_score, dedup_threshold, supersede_threshold)
            if action == "duplicate":
                return SaveResult(id=nearest_id, duplicate=True, redacted=redacted)
            if action == "supersede":
                superseded = nearest_id
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
        if superseded is not None:
            old = self.rows[superseded]
            old["valid_until"] = datetime.now(UTC)
            old["superseded_by"] = memory_id
        return SaveResult(
            id=memory_id, duplicate=False, superseded=superseded, redacted=redacted
        )

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

    async def purge(self, memory_id: str, reason: str) -> bool:
        """23e : suppression réelle + audit redacted (fake de memory_purge_audit)."""
        row = self.rows.get(memory_id)
        if row is None:
            return False
        cleaned, _ = scrub_content(row["content"])
        del self.rows[memory_id]
        self.audit.append(
            {
                "memory_id": memory_id,
                "content_redacted": cleaned,
                "reason": reason,
            }
        )
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


# --- 23e : supersede auto (zone intermédiaire), scrub secrets, purge RGPD ---


def test_dedup_action_trois_zones():
    assert dedup_action(0.99) == "duplicate"
    assert dedup_action(0.97) == "duplicate"
    assert dedup_action(0.90) == "supersede"
    assert dedup_action(SUPERSEDE_THRESHOLD) == "supersede"
    assert dedup_action(0.84) == "insert"
    assert dedup_action(0.0) == "insert"


def test_scrub_content_masque_secrets_et_pii():
    redactor = RegexRedactor(secrets=[])
    text = "ma clé sk-ant-abcdef1234567890xx et mail jean@exemple.fr"
    cleaned, changed = scrub_content(text, redactor=redactor)
    assert changed is True
    assert "sk-ant-abcdef1234567890xx" not in cleaned
    assert "jean@exemple.fr" not in cleaned
    assert cleaned.count(REDACTED) >= 2
    clean, changed2 = scrub_content("AAPL clôture à 344.63 $", redactor=redactor)
    assert changed2 is False
    assert clean == "AAPL clôture à 344.63 $"  # pas de faux positif


async def test_save_zone_intermediaire_supersede_automatiquement(store):
    v1 = [1.0] + [0.0] * 1535
    v2 = [0.9, math.sqrt(1 - 0.81)] + [0.0] * 1534  # cos(v1, v2) = 0.9
    r1 = await store.save("fait A", v1)
    assert r1.duplicate is False and r1.superseded is None
    r2 = await store.save("fait A v2", v2)  # 0.9 ∈ [0.85, 0.97) → supersede
    assert r2.duplicate is False
    assert r2.superseded == r1.id
    old = store.rows[r1.id]
    assert old["valid_until"] is not None
    assert old["superseded_by"] == r2.id
    recalled = await store.recall("fait A", k=5)
    assert all(r["id"] != r1.id for r in recalled)  # l'ancien n'est plus courant


async def test_save_quasi_identique_reste_noop(store):
    r1 = await store.save("fait A", None)
    r2 = await store.save("fait A", None)  # même contenu → cos 1.0 → duplicate
    assert r2.duplicate is True
    assert r2.superseded is None
    assert r2.id == r1.id


async def test_purge_hard_supprime_et_audite(store):
    r = await store.save("secret sk-ant-abcdef1234567890zz", None)
    ok = await store.purge(r.id, reason="demande RGPD")
    assert ok is True
    assert r.id not in store.rows  # suppression réelle
    assert store.audit and store.audit[0]["memory_id"] == r.id
    assert store.audit[0]["reason"] == "demande RGPD"
    assert "sk-ant-" not in store.audit[0]["content_redacted"]  # audit redacted
    assert await store.recall("secret", include_history=True) == []
    assert await store.history(r.id) == []


async def test_purge_inconnu_retourne_false(store):
    assert await store.purge("mem-999", reason="x") is False


async def test_forget_memory_hard_appelle_purge(store, embeddings):
    r = await store.save("fait", None)
    tool = ForgetMemoryTool(store, embeddings)
    out = await tool.run(ForgetMemoryArgs(memory_id=r.id, hard=True))
    assert out["purged"] is True
    assert r.id not in store.rows


async def test_forget_memory_soft_par_defaut_inchange(store, embeddings):
    """Zéro régression 16a : sans hard, forget reste un soft delete."""
    r = await store.save("fait 2", None)
    tool = ForgetMemoryTool(store, embeddings)
    out = await tool.run(ForgetMemoryArgs(memory_id=r.id))
    assert out == {"forgotten": True}
    assert r.id in store.rows  # la ligne reste en base
    assert store.rows[r.id]["valid_until"] is not None
