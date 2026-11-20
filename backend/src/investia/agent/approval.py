"""Registre des validations humaines en attente (étape 5.1, D57).

La boucle d'agent s'arrête sur simulate_order et attend ici la décision de
l'utilisateur (endpoint POST /agent/runs/{run_id}/approval). En mémoire :
un redémarrage du backend fait tomber les attentes en cours (timeout = refus).
"""

import asyncio
import hashlib
import json
import secrets

DECISIONS = ("approved", "refused")


def payload_hash_for(symbol: str, side: str, quantity: float) -> str:
    """Hash SHA-256 canonique du payload d'un ordre (anti replan-after-yes, 13d).

    Le symbole est normalisé (comme dans la boucle) pour que « aapl » et
    « AAPL » aient le même hash.
    """
    canonical = json.dumps(
        {"quantity": quantity, "side": side, "symbol": symbol.strip().upper()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class ApprovalRegistry:
    """run_id -> file d'attente de la décision (une seule décision par run).

    13d : la décision peut être liée au hash exact du payload approuvé
    (`open(run_id, payload_hash=...)`) : `decide` avec un hash différent
    retourne False (409 côté endpoint).
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[str]] = {}
        self._decisions: dict[str, str] = {}
        self._pending_hash: dict[str, str | None] = {}
        self._approved_hash: dict[str, str | None] = {}
        # 24 (scan sécurité) : bearer token à usage unique, émis dans
        # approval_request (SSE) et exigé par decide — le run_id seul ne suffit
        # plus à approuver (CWE-862).
        self._tokens: dict[str, str] = {}

    def open(self, run_id: str, payload_hash: str | None = None) -> str:
        """La boucle ouvre l'attente pour ce run (hash du payload affiché, 13d).

        Retourne le `approval_token` (secrets, usage unique) à transmettre au
        décideur via l'event approval_request.
        """
        self._queues.setdefault(run_id, asyncio.Queue())
        self._pending_hash[run_id] = payload_hash
        token = secrets.token_urlsafe(32)
        self._tokens[run_id] = token
        return token

    def close(self, run_id: str) -> None:
        """La boucle a fini (décision reçue ou timeout) : on nettoie."""
        self._queues.pop(run_id, None)
        self._pending_hash.pop(run_id, None)
        self._tokens.pop(run_id, None)

    def has(self, run_id: str) -> bool:
        """Vrai si une attente est ouverte pour ce run (sinon 404 côté endpoint)."""
        return run_id in self._queues

    def approval_token(self, run_id: str) -> str | None:
        """Token d'approbation courant du run (None si aucune attente)."""
        return self._tokens.get(run_id)

    def check_token(self, run_id: str, token: str | None) -> bool:
        """Vrai si `token` est le bearer token de l'attente (temps constant)."""
        expected = self._tokens.get(run_id)
        if expected is None or not token:
            return False
        return secrets.compare_digest(token.encode(), expected.encode())

    def approved_hash(self, run_id: str) -> str | None:
        """Hash du payload lié à la décision enregistrée (None si absent, 13d)."""
        return self._approved_hash.get(run_id)

    async def decide(
        self,
        run_id: str,
        decision: str,
        payload_hash: str | None = None,
        *,
        token: str | None = None,
    ) -> bool:
        """Enregistre la décision. False si run inconnu, déjà décidé (409),
        token invalide (403), ou hash fourni différent du hash de la demande
        en attente (409, 13d)."""
        if decision not in DECISIONS:
            raise ValueError(f"décision invalide : {decision!r}")
        if run_id not in self._queues or run_id in self._decisions:
            return False
        if not self.check_token(run_id, token):
            return False
        pending = self._pending_hash.get(run_id)
        if pending is not None and payload_hash is not None and payload_hash != pending:
            return False
        self._decisions[run_id] = decision
        if payload_hash is not None:
            self._approved_hash[run_id] = payload_hash
        else:
            self._approved_hash[run_id] = pending
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
