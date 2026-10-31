"""Client Jev (TypeSafe) via le gateway LiteLLM — endpoint /v1/systemone.

Jev ne rédige pas : on envoie un state + des questions typées, il renvoie des
probabilités calibrées. Routage confirmé le 31/10/2026 (Q10/D37) : LiteLLM sert
`jev` en mode evaluation et proxifie vers typesafe/jev-latest.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from investia.llm.client import RETRYABLE_STATUS
from investia.llm.errors import LlmError


@dataclass(frozen=True)
class JevAnswer:
    value: Any
    probabilities: dict[str, float]
    confidence: float


class JevClient:
    """Appelle Jev via LiteLLM (un seul point d'appel, cost tracking centralisé)."""

    def __init__(
        self,
        base_url: str,
        master_key: SecretStr,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._master_key = master_key
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def decide(
        self, state: Any, questions: dict[str, dict[str, Any]]
    ) -> dict[str, JevAnswer]:
        """Envoie un state + des questions typées, renvoie les réponses par id.

        Format System One : questions = {id: {"type": "choice"|"noul"|"score", ...}}.
        Choice : {"type": "choice", "instructions": "...", "criteria": {label: desc}}.
        """
        payload = {"model": "jev", "state": state, "questions": questions}
        response = await self._post_with_retry(payload)
        data = response.json()
        answers = data.get("answers", {})
        result: dict[str, JevAnswer] = {}
        for question_id, raw in answers.items():
            result[question_id] = JevAnswer(
                value=raw.get("value"),
                probabilities={
                    k: float(v) for k, v in raw.get("probabilities", {}).items()
                },
                confidence=float(raw.get("confidence", 0.0)),
            )
        return result

    async def _post_with_retry(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._master_key.get_secret_value()}"}
        last_error: LlmError | None = None
        for attempt in range(self._max_retries):
            response = await self._client.post(
                f"{self._base_url}/v1/systemone", json=payload, headers=headers
            )
            if response.status_code == 200:
                return response
            last_error = LlmError(f"jev via gateway HTTP {response.status_code}")
            is_last = attempt == self._max_retries - 1
            if response.status_code not in RETRYABLE_STATUS or is_last:
                raise last_error
            await asyncio.sleep(self._retry_delay)
        raise last_error if last_error else LlmError("jev: pas de réponse du gateway")
