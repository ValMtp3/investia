"""Client LiteLLM (gateway self-hosté, API OpenAI) avec retry, coût et budget."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from investia.llm.errors import LlmError
from investia.llm.models import ModelsConfig

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ToolCall:
    """Un appel d'outil demandé par le modèle (function calling)."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LlmResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_cents: float
    tool_calls: list[ToolCall] = field(default_factory=list)


class LlmClient:
    def __init__(
        self,
        base_url: str,
        master_key: SecretStr,
        models: ModelsConfig,
        budget_cents: float = 100.0,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._master_key = master_key
        self._models = models
        self._budget_cents = budget_cents
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def chat(
        self,
        model_key: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        model = self._models.by_key(model_key)
        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        response = await self._post_with_retry(payload)
        data = response.json()
        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            usage = data["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
            tool_calls = [
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=json.loads(call["function"]["arguments"]),
                )
                for call in message.get("tool_calls", [])
            ]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise LlmError(f"réponse mal formée du gateway ({model.name})") from error
        cost_cents = self._cost_cents(model, prompt_tokens, completion_tokens)
        if cost_cents > self._budget_cents:
            raise LlmError(
                f"budget dépassé : {cost_cents:.2f} c > {self._budget_cents:.2f} c "
                f"(modèle {model.name})"
            )
        return LlmResponse(
            content=content,
            model=model.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_cents=cost_cents,
            tool_calls=tool_calls,
        )

    def _cost_cents(self, model, prompt_tokens: int, completion_tokens: int) -> float:
        dollars = (
            prompt_tokens * model.price_input_per_m
            + completion_tokens * model.price_output_per_m
        ) / 1_000_000
        return dollars * 100

    async def _post_with_retry(self, payload: dict[str, Any]) -> httpx.Response:
        last_error: LlmError | None = None
        for attempt in range(self._max_retries):
            response = await self._client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._master_key.get_secret_value()}"
                },
            )
            if response.status_code == 200:
                return response
            last_error = LlmError(
                f"gateway HTTP {response.status_code} (modèle {payload['model']})"
            )
            if (
                response.status_code not in RETRYABLE_STATUS
                or attempt == self._max_retries - 1
            ):
                raise last_error
            await asyncio.sleep(self._retry_delay)
        raise last_error if last_error else LlmError("appel gateway sans réponse")
