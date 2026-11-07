"""Registre des validations humaines en attente (étape 5.1, D57).

La boucle d'agent s'arrête sur simulate_order et attend ici la décision de
l'utilisateur (endpoint POST /agent/runs/{run_id}/approval). En mémoire :
un redémarrage du backend fait tomber les attentes en cours (timeout = refus).
"""

import asyncio

DECISIONS = ("approved", "refused")


class ApprovalRegistry:
    """run_id -> file d'attente de la décision (une seule décision par run)."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[str]] = {}
        self._decisions: dict[str, str] = {}

    def open(self, run_id: str) -> None:
        """La boucle ouvre l'attente pour ce run."""
        self._queues.setdefault(run_id, asyncio.Queue())

    def close(self, run_id: str) -> None:
        """La boucle a fini (décision reçue ou timeout) : on nettoie."""
        self._queues.pop(run_id, None)

    def has(self, run_id: str) -> bool:
        """Vrai si une attente est ouverte pour ce run (sinon 404 côté endpoint)."""
        return run_id in self._queues

    async def decide(self, run_id: str, decision: str) -> bool:
        """Enregistre la décision. False si run inconnu ou déjà décidé (409)."""
        if decision not in DECISIONS:
            raise ValueError(f"décision invalide : {decision!r}")
        if run_id not in self._queues or run_id in self._decisions:
            return False
        self._decisions[run_id] = decision
        await self._queues[run_id].put(decision)
        return True

    async def wait(self, run_id: str, timeout: float) -> str:
        """Attend la décision ; « timeout » si personne ne répond dans le délai."""
        queue = self._queues.get(run_id)
        if queue is None:
            return "timeout"
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            return "timeout"
