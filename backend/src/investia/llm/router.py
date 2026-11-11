"""Routeur petit/gros modèle — règles en dur (étape 1.5, D44) + routeur appris (12h)."""

from dataclasses import dataclass
from typing import Protocol

SMALL_KEYWORDS = (
    "résume",
    "resume",
    "liste",
    "extrais",
    "traduis",
    "explique simplement",
)
LARGE_KEYWORDS = (
    "analyse",
    "profond",
    "stratégie",
    "recommande",
    "compare",
    "scénario",
)


def choose(question: str) -> str:
    """Renvoie "small" ou "large" selon la question."""
    q = question.lower()
    if any(k in q for k in LARGE_KEYWORDS):
        return "large"
    if any(k in q for k in SMALL_KEYWORDS):
        return "small"
    return "small" if len(q) < 120 else "large"


# --- Étape 12h : routeur appris (k-NN sémantique pondéré sur router_feedback) ---

K_NEIGHBORS = 7
MIN_FEEDBACKS = 5
MIN_SCORE_GAP = 0.1


@dataclass(frozen=True)
class Neighbor:
    """Un feedback passé proche de la question courante."""

    similarity: float
    model: str
    success: bool


class RouterFeedbackStore(Protocol):
    async def record(self, question: str, model: str, success: bool) -> None: ...

    async def neighbors(self, question: str, k: int) -> list[Neighbor]: ...


class LearnedRouter:
    """Choisit small/large selon les succès passés des questions les plus proches.

    score(modele) = Σ(similarité × succès) / Σ(similarités) sur les k voisins.
    Fallback sur les règles (D44) si moins de min_feedbacks voisins ou si
    l'écart entre les deux scores est < min_gap.
    """

    def __init__(
        self,
        store: RouterFeedbackStore,
        fallback=choose,
        k: int = K_NEIGHBORS,
        min_feedbacks: int = MIN_FEEDBACKS,
        min_gap: float = MIN_SCORE_GAP,
    ) -> None:
        self._store = store
        self._fallback = fallback
        self._k = k
        self._min_feedbacks = min_feedbacks
        self._min_gap = min_gap

    async def choose(self, question: str) -> tuple[str, str]:
        """Renvoie (model_key, source) avec source = 'learned' ou 'rules'."""
        neighbors = await self._store.neighbors(question, self._k)
        if len(neighbors) < self._min_feedbacks:
            return self._fallback(question), "rules"
        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for neighbor in neighbors:
            weight = max(0.0, neighbor.similarity)
            num[neighbor.model] = num.get(neighbor.model, 0.0) + weight * (
                1.0 if neighbor.success else 0.0
            )
            den[neighbor.model] = den.get(neighbor.model, 0.0) + weight
        score_small = num.get("small", 0.0) / den["small"] if den.get("small") else 0.0
        score_large = num.get("large", 0.0) / den["large"] if den.get("large") else 0.0
        if abs(score_small - score_large) < self._min_gap:
            return self._fallback(question), "rules"
        return ("small" if score_small >= score_large else "large"), "learned"

    async def record(self, question: str, model: str, success: bool) -> None:
        await self._store.record(question, model, success)
