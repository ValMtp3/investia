"""Routeur LinUCB/ε-explore au-dessus du k-NN (chantier 23d, veille D94).

Pourquoi : le k-NN 12h extrapole les succès passés des questions proches, mais ne
modélise pas le coût. LinUCB apprend un modèle linéaire par bras (small/large) sur
un petit vecteur de features (dont les prix effectifs à l'heure UTC — remise
off-peak DeepSeek −50 % hors 01:00–04:00 et 06:00–10:00 UTC lun–ven) et explore
avec probabilité ε. Anti-windup (boucle fermée stable, pattern OrcaRouter) :
reward clampé dans [0, 1], α fixe, et un bras dont la matrice devient singulière
est reset (redevenu froid).

Cœur 100 % stdlib : d = 7, donc on résout A·θ = b par Gauss-Jordan à chaque
choose (O(d³) négligeable) plutôt que de maintenir A⁻¹ incrémentalement.
"""

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from investia.llm.models import ModelConfig, ModelsConfig
from investia.llm.router import K_NEIGHBORS, RouterFeedbackStore, choose

D_FEATURES = 7
ARMS = ("small", "large")

# Fenêtres plein tarif UTC en semaine (veille D94) ; hors de ces fenêtres le
# modèle small (DeepSeek) bénéficie de la remise off-peak de −50 %.
PEAK_WINDOWS_UTC = ((1.0, 4.0), (6.0, 10.0))
OFF_PEAK_DISCOUNT = 0.5
DISCOUNT_ARMS = frozenset({"small"})

SINGULAR_PIVOT = 1e-12


def is_peak(now: datetime) -> bool:
    """True si `now` (UTC) tombe dans une fenêtre plein tarif lun–ven."""
    if now.weekday() >= 5:  # samedi=5, dimanche=6 -> off-peak
        return False
    hour = now.hour + now.minute / 60 + now.second / 3600
    return any(start <= hour < end for start, end in PEAK_WINDOWS_UTC)


def effective_price(model: ModelConfig, arm: str, now: datetime) -> float:
    """Prix input effectif du modèle à l'instant `now` (remise off-peak incluse)."""
    if arm in DISCOUNT_ARMS and not is_peak(now):
        return model.price_input_per_m * OFF_PEAK_DISCOUNT
    return model.price_input_per_m


def estimate_cost_cents(
    question: str, model: ModelConfig, arm: str, now: datetime
) -> float:
    """Coût estimé d'une requête (entrée ~ len/4 tokens + 400 tokens de sortie)."""
    tokens_in = max(1.0, len(question) / 4)
    tokens_out = 400.0
    price_in = effective_price(model, arm, now)
    return (tokens_in * price_in + tokens_out * model.price_output_per_m) / 1e6 * 100.0


@dataclass(frozen=True)
class FeatureContext:
    knn_small: float
    knn_large: float
    now: datetime
    models: ModelsConfig
    budget_cents: float
    cost_estimate_cents: float


def build_features(question: str, ctx: FeatureContext) -> list[float]:
    """Vecteur de features d=7, toutes les composantes dans [0, 1]."""
    small = ctx.models.small
    large = ctx.models.large
    price_small = effective_price(small, "small", ctx.now)
    price_large = effective_price(large, "large", ctx.now)
    return [
        1.0,  # biais
        min(1.0, max(0.0, ctx.knn_small)),
        min(1.0, max(0.0, ctx.knn_large)),
        min(len(question), 500) / 500.0,
        price_small / small.price_input_per_m if small.price_input_per_m else 1.0,
        price_large / large.price_input_per_m if large.price_input_per_m else 1.0,
        (
            min(ctx.cost_estimate_cents, ctx.budget_cents) / ctx.budget_cents
            if ctx.budget_cents > 0
            else 0.0
        ),
    ]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gauss-Jordan avec pivot partiel. Lève ValueError si singulière."""
    n = len(vector)
    augmented = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot][col]) < SINGULAR_PIVOT:
            raise ValueError("matrice singulière")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        augmented[col] = [v / pivot_value for v in augmented[col]]
        for r in range(n):
            if r != col and augmented[r][col] != 0.0:
                factor = augmented[r][col]
                augmented[r] = [
                    v - factor * w for v, w in zip(augmented[r], augmented[col])
                ]
    return [augmented[i][n] for i in range(n)]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class LinUCB:
    """LinUCB à 2 bras sur des features normalisées (d petit, solve exact)."""

    def __init__(
        self,
        d: int = D_FEATURES,
        arms: tuple[str, ...] = ARMS,
        alpha: float = 0.5,
        epsilon: float = 0.05,
        lam: float = 1.0,
    ) -> None:
        self.d = d
        self.arms = tuple(arms)
        self.alpha = alpha
        self.epsilon = epsilon
        self.lam = lam
        self._state: dict[str, dict[str, Any]] = {
            arm: self._cold_state() for arm in self.arms
        }

    def _cold_state(self) -> dict[str, Any]:
        return {
            "A": [
                [self.lam if i == j else 0.0 for j in range(self.d)]
                for i in range(self.d)
            ],
            "b": [0.0] * self.d,
            "n": 0,
        }

    def state(self, arm: str) -> dict[str, Any]:
        return self._state[arm]

    @property
    def total_n(self) -> int:
        return sum(s["n"] for s in self._state.values())

    def choose(self, x: list[float], rng: random.Random) -> tuple[str, str]:
        """(bras, source) avec source = 'explore' (proba ε) ou 'linucb' (argmax UCB)."""
        if rng.random() < self.epsilon:
            return rng.choice(self.arms), "explore"
        best_arm: str | None = None
        best_value = -math.inf
        for arm in self.arms:
            state = self._state[arm]
            try:
                theta = _solve(state["A"], state["b"])
                y = _solve(state["A"], x)
            except ValueError:
                # anti-windup : bras singulier -> reset, redevenu froid
                self._state[arm] = self._cold_state()
                state = self._state[arm]
                theta = _solve(state["A"], state["b"])
                y = _solve(state["A"], x)
            bonus = self.alpha * math.sqrt(max(0.0, _dot(x, y)))
            value = _dot(x, theta) + bonus
            if value > best_value:
                best_arm, best_value = arm, value
        assert best_arm is not None
        return best_arm, "linucb"

    def update(self, arm: str, x: list[float], reward: float) -> None:
        """Mise à jour rank-1 ; reward clampé dans [0, 1] (anti-windup)."""
        clamped = min(1.0, max(0.0, reward))
        state = self._state[arm]
        for i in range(self.d):
            for j in range(self.d):
                state["A"][i][j] += x[i] * x[j]
            state["b"][i] += clamped * x[i]
        state["n"] += 1

    def load_state(self, arm: str, state: dict[str, Any]) -> None:
        matrix = state["A"]
        vector = state["b"]
        if (
            len(matrix) != self.d
            or any(len(row) != self.d for row in matrix)
            or len(vector) != self.d
        ):
            raise ValueError(f"état incompatible avec d={self.d}")
        self._state[arm] = {
            "A": [list(row) for row in matrix],
            "b": list(vector),
            "n": int(state["n"]),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "d": self.d,
            "arms": list(self.arms),
            "alpha": self.alpha,
            "epsilon": self.epsilon,
            "lam": self.lam,
            "state": {
                arm: {
                    "A": [list(row) for row in s["A"]],
                    "b": list(s["b"]),
                    "n": s["n"],
                }
                for arm, s in self._state.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinUCB":
        obj = cls(
            d=data["d"],
            arms=tuple(data["arms"]),
            alpha=data["alpha"],
            epsilon=data["epsilon"],
            lam=data["lam"],
        )
        for arm, state in data["state"].items():
            if arm in obj.arms:
                obj.load_state(arm, state)
        return obj


class LinUCBStateStore(Protocol):
    """Persistance des états LinUCB (A aplati, b, n) par bras."""

    async def load_all(self) -> dict[str, dict[str, Any]]: ...

    async def save(self, arm: str, state: dict[str, Any]) -> None: ...


def _knn_scores(neighbors: list[Any]) -> tuple[float, float]:
    """Scores k-NN pondérés par bras (même calcul que LearnedRouter 12h)."""
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    for neighbor in neighbors:
        weight = max(0.0, neighbor.similarity)
        num[neighbor.model] = num.get(neighbor.model, 0.0) + weight * (
            1.0 if neighbor.success else 0.0
        )
        den[neighbor.model] = den.get(neighbor.model, 0.0) + weight
    small = num.get("small", 0.0) / den["small"] if den.get("small") else 0.0
    large = num.get("large", 0.0) / den["large"] if den.get("large") else 0.0
    return small, large


class LinUCBRouter:
    """Routeur LinUCB au-dessus du k-NN 12h — même interface que LearnedRouter.

    choose(question) -> (model_key, source) avec source ∈ rules | linucb | explore.
    record(question, model, success, cost_cents) écrit le feedback k-NN (avec le
    coût) ET met à jour le bras LinUCB : reward = succès − cost_weight·coût/budget,
    clampé dans [0, 1] par LinUCB.update.
    """

    def __init__(
        self,
        feedback_store: RouterFeedbackStore,
        linucb_store: LinUCBStateStore,
        *,
        models: ModelsConfig,
        fallback: Callable[[str], str] = choose,
        alpha: float = 0.5,
        epsilon: float = 0.05,
        cost_weight: float = 0.1,
        budget_cents: float = 100.0,
        min_feedbacks: int = 5,
        k: int = K_NEIGHBORS,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._feedback = feedback_store
        self._store = linucb_store
        self._models = models
        self._fallback = fallback
        self._cost_weight = cost_weight
        self._budget = budget_cents
        self._min_feedbacks = min_feedbacks
        self._k = k
        self._rng = rng or random.Random()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.linucb = LinUCB(alpha=alpha, epsilon=epsilon)
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            for arm, state in (await self._store.load_all()).items():
                if arm in self.linucb.arms:
                    self.linucb.load_state(arm, state)
            self._loaded = True

    def _features(
        self, question: str, knn_small: float, knn_large: float
    ) -> list[float]:
        now = self._clock()
        estimate = estimate_cost_cents(question, self._models.small, "small", now)
        ctx = FeatureContext(
            knn_small=knn_small,
            knn_large=knn_large,
            now=now,
            models=self._models,
            budget_cents=self._budget,
            cost_estimate_cents=estimate,
        )
        return build_features(question, ctx)

    async def choose(self, question: str) -> tuple[str, str]:
        await self._ensure_loaded()
        if self.linucb.total_n < self._min_feedbacks:
            return self._fallback(question), "rules"
        neighbors = await self._feedback.neighbors(question, self._k)
        knn_small, knn_large = _knn_scores(neighbors)
        x = self._features(question, knn_small, knn_large)
        return self.linucb.choose(x, self._rng)

    async def record(
        self, question: str, model: str, success: bool, cost_cents: float = 0.0
    ) -> None:
        await self._feedback.record(question, model, success, cost_cents=cost_cents)
        await self._ensure_loaded()
        neighbors = await self._feedback.neighbors(question, self._k)
        knn_small, knn_large = _knn_scores(neighbors)
        x = self._features(question, knn_small, knn_large)
        reward = (1.0 if success else 0.0) - (
            self._cost_weight * min(cost_cents, self._budget) / self._budget
            if self._budget > 0
            else 0.0
        )
        self.linucb.update(model, x, reward)
        await self._store.save(model, self.linucb.state(model))
