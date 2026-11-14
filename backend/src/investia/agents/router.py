"""Routeur d'agents A2A (étape 18a, P9 piste 1) : délégation dynamique pilotée
par les feedbacks passés — même pattern k-NN pondéré que le routeur de modèles
(12h, D76).

`FixedPipelineRouter` = comportement historique (analyste → risque → rédacteur).
`LearnedAgentRouter` choisit les agents dont le score pondéré dépasse
`min_score` ; l'agent « risque » reste toujours la gate bloquante quand du
routing learned est retenu. Fallback sur le pipeline fixe si pas assez de
preuves (< min_feedbacks voisins ou aucun agent au-dessus du seuil).
"""

from dataclasses import dataclass
from typing import Protocol

# Ordre canonique du pipeline fixe (6.1, D60).
CANONICAL_PIPELINE = ["analyste", "risque", "redacteur"]
RISK_AGENT = "risque"

K_NEIGHBORS = 7
MIN_FEEDBACKS = 5
DEFAULT_MIN_SCORE = 0.5


@dataclass(frozen=True)
class AgentNeighbor:
    """Un feedback passé proche de la question courante."""

    similarity: float
    agent: str
    success: bool


class AgentFeedbackStore(Protocol):
    async def record(self, question: str, agents: list[str], success: bool) -> None: ...

    async def neighbors(self, question: str, k: int) -> list[AgentNeighbor]: ...


class AgentRouter(Protocol):
    async def choose(self, question: str) -> tuple[list[str], str]: ...

    async def record(self, question: str, agents: list[str], success: bool) -> None: ...


class FixedPipelineRouter:
    """Pipeline fixe historique : toujours les 3 agents, source « fixed »."""

    async def choose(self, question: str) -> tuple[list[str], str]:
        return list(CANONICAL_PIPELINE), "fixed"

    async def record(self, question: str, agents: list[str], success: bool) -> None:
        return None  # pas de store : rien à enregistrer


class LearnedAgentRouter:
    """Choisit les agents selon leurs succès passés sur les questions proches.

    score(agent) = Σ(similarité × succès) / Σ(similarités) sur les k voisins.
    Retenus : agents avec score ≥ min_score, dans l'ordre canonique, plus
    toujours l'agent risque (gate). Aucun retenu → fallback pipeline fixe.
    """

    def __init__(
        self,
        store: AgentFeedbackStore,
        fallback: AgentRouter | None = None,
        k: int = K_NEIGHBORS,
        min_feedbacks: int = MIN_FEEDBACKS,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> None:
        self._store = store
        self._fallback = fallback or FixedPipelineRouter()
        self._k = k
        self._min_feedbacks = min_feedbacks
        self._min_score = min_score

    async def choose(self, question: str) -> tuple[list[str], str]:
        neighbors = await self._store.neighbors(question, self._k)
        if len(neighbors) < self._min_feedbacks:
            return await self._fallback.choose(question)
        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for neighbor in neighbors:
            weight = max(0.0, neighbor.similarity)
            num[neighbor.agent] = num.get(neighbor.agent, 0.0) + weight * (
                1.0 if neighbor.success else 0.0
            )
            den[neighbor.agent] = den.get(neighbor.agent, 0.0) + weight
        selected = {
            agent
            for agent in den
            if den[agent] > 0 and num[agent] / den[agent] >= self._min_score
        }
        if not selected:
            return await self._fallback.choose(question)
        # ordre canonique, gate risque toujours présente si du learned est retenu
        chosen = [a for a in CANONICAL_PIPELINE if a in selected]
        if RISK_AGENT not in chosen:
            chosen.insert(1 if chosen else 0, RISK_AGENT)
        return chosen, "learned"

    async def record(self, question: str, agents: list[str], success: bool) -> None:
        await self._store.record(question, agents, success)
