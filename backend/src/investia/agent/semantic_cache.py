"""Cache sémantique des réponses de l'agent (étape 12e, durci en 23g).

Une question très proche d'une question déjà répondue (similarité cosinus
>= CACHE_THRESHOLD) est servie sans appel LLM. On ne stocke que des réponses
qui ont passé les garde-fous (status ok) — la responsabilité du store est à
l'appelant (la boucle).

23g (CVE-2026-89032) : entrées namespacées (`namespace`, migration 0014) et
`BudgetedSemanticCache` — error budget fail-open (arXiv:2601.23088/2611.02498).
"""

import logging
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from investia.memory.embeddings import Embeddings

# Seuil haut : en finance, deux questions proches ne sont pas identiques.
CACHE_THRESHOLD = 0.92


class SemanticCacheProtocol(Protocol):
    async def lookup(self, question: str) -> str | None: ...

    async def store(self, question: str, answer: str) -> None: ...


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


class DbSemanticCache:
    """Cache sémantique en PostgreSQL (pgvector), même pattern que DbMemoryStore.

    23g : chaque entrée porte un `namespace` (CVE-2026-89032 : pas de fuite
    cross-user) — le namespace est lié à l'instance (par déploiement ; le
    multi-user passera le namespace par requête plus tard).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        embeddings: Embeddings,
        threshold: float = CACHE_THRESHOLD,
        namespace: str = "default",
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._threshold = threshold
        self._namespace = namespace

    async def lookup(self, question: str) -> str | None:
        query_vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT answer, "
                            "1 - (embedding <=> CAST(:e AS vector)) AS score "
                            "FROM semantic_cache WHERE namespace = :ns "
                            "ORDER BY embedding <=> CAST(:e AS vector) LIMIT 1"
                        ),
                        {"e": _vector_literal(query_vector), "ns": self._namespace},
                    )
                )
                .mappings()
                .first()
            )
        if row is None or float(row["score"]) < self._threshold:
            return None
        return str(row["answer"])

    async def store(self, question: str, answer: str) -> None:
        vector = (await self._embeddings.embed([question]))[0]
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO semantic_cache "
                    "(question, answer, embedding, namespace) "
                    "VALUES (:q, :a, CAST(:e AS vector), :ns)"
                ),
                {
                    "q": question,
                    "a": answer,
                    "e": _vector_literal(vector),
                    "ns": self._namespace,
                },
            )
            await session.commit()


# --- 23g : error budget (arXiv:2601.23088/2611.02498) ---------------------------

DEFAULT_ERROR_BUDGET = 5


class BudgetedSemanticCache:
    """Enveloppe fail-open avec error budget sur un SemanticCacheProtocol.

    Chaque erreur consécutive de lookup/store est comptée ; au-delà de
    `error_budget`, le cache passe en mode dégradé (lookup -> None, store no-op,
    warning loggé une fois) : un cache en panne ne casse jamais un run et ne
    coûte plus aucune requête. Un succès remet le compteur à 0.
    """

    def __init__(
        self, inner: SemanticCacheProtocol, error_budget: int = DEFAULT_ERROR_BUDGET
    ) -> None:
        self.inner = inner
        self._error_budget = error_budget
        self._errors = 0  # cumul (stats)
        self._consecutive_errors = 0  # compteur du budget
        self._degraded = False
        self._lookups = 0
        self._hits = 0

    def stats(self) -> dict[str, Any]:
        return {
            "lookups": self._lookups,
            "hits": self._hits,
            "errors": self._errors,
            "degraded": self._degraded,
        }

    def _on_error(self) -> None:
        self._errors += 1
        self._consecutive_errors += 1
        if not self._degraded and self._consecutive_errors >= self._error_budget:
            self._degraded = True
            logging.getLogger(__name__).warning(
                "cache sémantique dégradé après %s erreurs consécutives "
                "(error budget atteint, fail-open)",
                self._consecutive_errors,
            )

    def _on_success(self) -> None:
        self._consecutive_errors = 0
        self._degraded = False

    async def lookup(self, question: str) -> str | None:
        if self._degraded:
            return None
        self._lookups += 1
        try:
            answer = await self.inner.lookup(question)
        except Exception:
            self._on_error()
            return None
        self._on_success()
        if answer is not None:
            self._hits += 1
        return answer

    async def store(self, question: str, answer: str) -> None:
        if self._degraded:
            return
        try:
            await self.inner.store(question, answer)
        except Exception:
            self._on_error()
            return
        self._on_success()


__all__ = [
    "CACHE_THRESHOLD",
    "BudgetedSemanticCache",
    "DbSemanticCache",
    "SemanticCacheProtocol",
]
