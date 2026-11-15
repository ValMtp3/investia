"""Tests TDD de la brique 12e : cache sémantique (DbSemanticCache + boucle + evals)."""

import math
from typing import Any

import pytest

from investia.agent.semantic_cache import CACHE_THRESHOLD, DbSemanticCache


class FakeEmbeddings:
    """Embeddings déterministes : hash du texte, vecteur normalisé."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [b / 255.0 for b in digest[:8]]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec] + [0.0] * 1528)
        return vectors


class FakeSemanticCache:
    """Cache en mémoire avec vraie similarité cosinus (pour tester la boucle)."""

    def __init__(self, threshold: float = CACHE_THRESHOLD):
        self.threshold = threshold
        self.entries: list[tuple[str, str, list[float]]] = []
        self.stored: list[tuple[str, str]] = []

    @staticmethod
    def _cos(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)

    async def lookup(self, question: str) -> str | None:
        qv = (await FakeEmbeddings().embed([question]))[0]
        best, best_score = None, -1.0
        for q, answer, vec in self.entries:
            score = self._cos(qv, vec)
            if score > best_score:
                best, best_score = answer, score
        if best is not None and best_score >= self.threshold:
            return best
        return None

    async def store(self, question: str, answer: str) -> None:
        vec = (await FakeEmbeddings().embed([question]))[0]
        self.entries.append((question, answer, vec))
        self.stored.append((question, answer))


def test_seuil_par_defaut_092():
    assert CACHE_THRESHOLD == 0.92


@pytest.mark.integration
async def test_integration_lookup_store_roundtrip():
    """Roundtrip réel pgvector : store puis lookup (identique -> hit, loin -> miss)."""
    from investia.db import get_session
    from investia.memory.embeddings import FakeEmbeddingsForTests

    cache = DbSemanticCache(get_session(), FakeEmbeddingsForTests())
    await cache.store("prix de AAPL ?", "AAPL vaut 344.63 $")
    hit = await cache.lookup("prix de AAPL ?")
    assert hit == "AAPL vaut 344.63 $"
    miss = await cache.lookup("quelle météo à Paris demain ?")
    assert miss is None


# --- Task 2 : boucle run_agent(semantic_cache=...) ---

from datetime import UTC, datetime  # noqa: E402

from investia.agent import run_agent  # noqa: E402
from investia.llm.client import LlmResponse, ToolCall  # noqa: E402
from investia.market.base import MarketData  # noqa: E402
from investia.tools import build_tools  # noqa: E402


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self, model_key, messages, temperature=0.2, tools=None, logprobs=False
    ):
        self.calls.append({"model": model_key})
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


FINAL_OK = """## Thèse
Le prix de AAPL est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""

FINAL_SANS_DISCLAIMER = """## Thèse
Le prix de AAPL est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub
"""


def make_response(content="", tool_calls=None, cost=0.01):
    return LlmResponse(
        content=content,
        model="mock",
        prompt_tokens=10,
        completion_tokens=5,
        cost_cents=cost,
        tool_calls=tool_calls or [],
    )


def llm_ok():
    return FakeLlm(
        [
            make_response(
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ]
            ),
            make_response(content=FINAL_OK),
        ]
    )


async def test_cache_hit_renvoie_sans_appel_llm():
    cache = FakeSemanticCache()
    cache.entries.append(
        (
            "prix de AAPL ?",
            "RÉPONSE CACHÉE",
            (await FakeEmbeddings().embed(["prix de AAPL ?"]))[0],
        )
    )
    llm = llm_ok()
    events = []

    async def sink(kind, payload):
        events.append(kind)

    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        semantic_cache=cache,
        event_sink=sink,
    )
    assert result.answer == "RÉPONSE CACHÉE"
    assert result.turns == 0
    assert result.total_cost_cents == 0.0
    assert result.model == "cache"
    assert result.from_cache is True
    assert result.status == "ok"
    assert len(llm.calls) == 0  # aucun appel LLM
    assert "cache_hit" in events
    assert cache.stored == []  # pas de re-store d'un hit


async def test_cache_miss_run_normal_puis_store_si_ok():
    cache = FakeSemanticCache()
    result = await run_agent(
        "prix de AAPL ?", llm_ok(), build_tools(FakeMarket()), semantic_cache=cache
    )
    assert result.from_cache is False
    assert result.status == "ok"
    assert cache.stored == [("prix de AAPL ?", FINAL_OK)]
    # et au 2e appel, la question est servie par le cache
    llm2 = llm_ok()
    result2 = await run_agent(
        "prix de AAPL ?", llm2, build_tools(FakeMarket()), semantic_cache=cache
    )
    assert result2.from_cache is True
    assert len(llm2.calls) == 0


async def test_pas_de_store_si_bloque():
    cache = FakeSemanticCache()
    llm = FakeLlm(
        [
            make_response(
                tool_calls=[
                    ToolCall(id="c1", name="get_quote", arguments={"symbol": "AAPL"})
                ]
            ),
            make_response(content=FINAL_SANS_DISCLAIMER),
        ]
    )
    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket()),
        semantic_cache=cache,
        max_corrections=0,
    )
    assert result.status == "blocked"
    assert cache.stored == []


async def test_erreur_cache_ne_plante_pas():
    class CacheKo:
        async def lookup(self, question):
            raise RuntimeError("pg down")

        async def store(self, question, answer):
            raise RuntimeError("pg down")

    result = await run_agent(
        "prix de AAPL ?", llm_ok(), build_tools(FakeMarket()), semantic_cache=CacheKo()
    )
    assert result.status == "ok"
    assert result.from_cache is False


async def test_sans_cache_rien_ne_change():
    llm = llm_ok()
    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    assert result.from_cache is False
    assert len(llm.calls) == 2


async def test_k3_lookup_store_une_seule_fois():
    lookups = []
    stores = []

    class CountingCache(FakeSemanticCache):
        async def lookup(self, question):
            lookups.append(question)
            return await super().lookup(question)

        async def store(self, question, answer):
            stores.append(question)
            return await super().store(question, answer)

    counting = CountingCache()

    def factory(i):
        return llm_ok()

    result = await run_agent(
        "prix de AAPL ?",
        FakeLlm([]),
        build_tools(FakeMarket()),
        consistency_k=3,
        llm_factory=factory,
        semantic_cache=counting,
    )
    assert result.consensus == 1.0
    assert lookups == ["prix de AAPL ?"]  # une seule fois, pas 3
    assert stores == ["prix de AAPL ?"]  # idem


# --- 23g : namespace + error budget + plancher de seuil (CVE-2026-89032) ------


class FlakyCache:
    """Cache inner qui échoue tant que `fail` > 0 (pour tester l'error budget)."""

    def __init__(self, fail: int = 0):
        self.fail = fail
        self.lookups = 0
        self.stores = 0

    async def lookup(self, question: str) -> str | None:
        self.lookups += 1
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("cache indisponible")
        return "réponse en cache"

    async def store(self, question: str, answer: str) -> None:
        self.stores += 1
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("cache indisponible")


async def test_budgeted_cache_degrade_apres_budget_erreurs_consecutives():
    from investia.agent.semantic_cache import BudgetedSemanticCache

    inner = FlakyCache(fail=5)
    cache = BudgetedSemanticCache(inner, error_budget=5)
    # 5 erreurs consécutives -> fail-open (None) puis mode dégradé
    for _ in range(5):
        assert await cache.lookup("q") is None
    stats = cache.stats()
    assert stats["errors"] == 5
    assert stats["degraded"] is True
    # en mode dégradé, on n'appelle plus le inner (fail-open, zéro coût)
    assert await cache.lookup("q") is None
    assert inner.lookups == 5
    await cache.store("q", "a")
    assert inner.stores == 0


async def test_budgeted_cache_recupere_apres_un_succes():
    from investia.agent.semantic_cache import BudgetedSemanticCache

    inner = FlakyCache(fail=3)
    cache = BudgetedSemanticCache(inner, error_budget=5)
    for _ in range(3):
        assert await cache.lookup("q") is None
    assert cache.stats()["degraded"] is False  # sous le budget
    assert await cache.lookup("q") == "réponse en cache"  # succès -> reset
    assert cache.stats() == {
        "lookups": 4,
        "hits": 1,
        "errors": 3,
        "degraded": False,
    }


async def test_budgeted_cache_store_delegue_et_compte():
    from investia.agent.semantic_cache import BudgetedSemanticCache

    inner = FlakyCache(fail=0)
    cache = BudgetedSemanticCache(inner, error_budget=5)
    await cache.store("q", "a")
    assert inner.stores == 1
    assert cache.stats()["hits"] == 0  # store ne compte pas un hit


def test_config_seuil_plancher_0_9(monkeypatch):
    from pydantic import ValidationError

    from investia.config import Settings

    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, semantic_cache_threshold=0.5)  # < 0,9 interdit
    ok = Settings(_env_file=None, semantic_cache_threshold=0.95)
    assert ok.semantic_cache_threshold == 0.95
    assert ok.semantic_cache_namespace == "default"


def test_config_namespace_pattern(monkeypatch):
    from pydantic import ValidationError

    from investia.config import Settings

    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, semantic_cache_namespace="mauvais ns!")
    ok = Settings(_env_file=None, semantic_cache_namespace="user-42")
    assert ok.semantic_cache_namespace == "user-42"


def test_build_semantic_cache_injecte_namespace_et_seuil(monkeypatch):
    from investia.agent.semantic_cache import BudgetedSemanticCache, DbSemanticCache
    from investia.config import Settings
    from investia.main import _build_semantic_cache

    class FakeSessionFactory:
        def __call__(self):
            raise AssertionError("pas de session en test unitaire")

    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    settings = Settings(
        _env_file=None,
        semantic_cache_threshold=0.93,
        semantic_cache_namespace="user-42",
    )
    cache = _build_semantic_cache(
        settings, session_factory=FakeSessionFactory(), embeddings=FakeEmbeddings()
    )
    assert isinstance(cache, BudgetedSemanticCache)
    inner = cache.inner
    assert isinstance(inner, DbSemanticCache)
    assert inner._namespace == "user-42"
    assert inner._threshold == 0.93


def test_build_semantic_cache_none_si_embeddings_indisponibles(monkeypatch):
    from investia.config import Settings
    from investia.main import _build_semantic_cache

    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("APP_SECRET_KEY", "test-admin-secret-0123456789abcdef")
    settings = Settings(_env_file=None)

    def boom(_settings):
        raise RuntimeError("pas d'embeddings")

    monkeypatch.setattr("investia.memory.build_memory", boom)
    # embeddings=None -> _build_semantic_cache tente build_memory -> exception -> None
    assert (
        _build_semantic_cache(settings, session_factory=None, embeddings=None) is None
    )


@pytest.mark.integration
async def test_integration_namespace_isole_les_caches():
    """Deux namespaces ne se voient pas (CVE-2026-89032 : pas de fuite cross-user)."""
    from investia.db import get_session
    from investia.memory.embeddings import FakeEmbeddingsForTests

    cache_a = DbSemanticCache(
        get_session(), FakeEmbeddingsForTests(), namespace="user-a"
    )
    cache_b = DbSemanticCache(
        get_session(), FakeEmbeddingsForTests(), namespace="user-b"
    )
    await cache_a.store("prix de AAPL ?", "AAPL vaut 344.63 $")
    assert await cache_a.lookup("prix de AAPL ?") == "AAPL vaut 344.63 $"
    assert await cache_b.lookup("prix de AAPL ?") is None  # isolé
