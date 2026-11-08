"""Adapters live (étape 8) : branchent le vrai client LLM investia (LiteLLM)
sur les modèles de Pydantic AI et OpenAI Agents SDK, pour les evals réelles.

Le client investia expose `chat(model_key, messages) -> LlmResponse`
(content, model, cost_cents, tool_calls). Chaque adapter convertit vers
l'interface du framework.
"""

import json
from typing import Any

from agents import Model, ModelResponse, ModelSettings
from agents.items import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from agents.usage import Usage
from pydantic_ai.messages import (
    ModelResponse as PaiModelResponse,
)
from pydantic_ai.messages import (
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models import Model as PaiModel
from pydantic_ai.models import ModelRequestParameters


def _to_messages(input_items: Any) -> list[dict[str, Any]]:
    """Convertit l'input pydantic-ai/agents (str ou liste d'items) en messages chat."""
    if isinstance(input_items, str):
        return [{"role": "user", "content": input_items}]
    messages: list[dict[str, Any]] = []
    for item in input_items or []:
        role = getattr(item, "role", None) or getattr(item, "kind", None)
        if role in ("user", "system"):
            parts = getattr(item, "parts", [])
            text = " ".join(
                str(getattr(p, "content", "")) for p in parts if hasattr(p, "content")
            )
            messages.append({"role": "user", "content": text})
        elif role == "assistant":
            content = getattr(item, "content", "") or ""
            messages.append({"role": "assistant", "content": content})
            for tc in getattr(item, "tool_calls", []) or []:
                messages[-1].setdefault("tool_calls", []).append(
                    {
                        "id": getattr(tc, "id", "call_1"),
                        "type": "function",
                        "function": {
                            "name": getattr(tc, "name", ""),
                            "arguments": json.dumps(getattr(tc, "args", {})),
                        },
                    }
                )
        elif role == "tool":
            messages.append(
                {"role": "tool", "content": str(getattr(item, "content", ""))}
            )
    return messages


class PydanticAiLiveModel(PaiModel):
    """Modèle pydantic-ai qui appelle le vrai LLM via le client investia."""

    def __init__(self, llm: Any):
        super().__init__()
        self._llm = llm

    @property
    def base_url(self) -> str:
        return "litellm"

    @property
    def model_name(self) -> str:
        return "litellm-live"

    @property
    def system(self) -> str:
        return "litellm"

    async def request(
        self,
        messages: list[Any],
        model_settings: Any,
        model_request_parameters: ModelRequestParameters,
    ) -> PaiModelResponse:
        conv = []
        for m in messages:
            for part in getattr(m, "parts", []):
                if getattr(part, "part_kind", "") == "user-prompt":
                    conv.append({"role": "user", "content": part.content})
                elif getattr(part, "part_kind", "") == "tool-return":
                    conv.append({"role": "tool", "content": str(part.content)})
                elif getattr(part, "part_kind", "") == "tool-call":
                    conv.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": part.tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": part.tool_name,
                                        "arguments": json.dumps(part.args),
                                    },
                                }
                            ],
                        }
                    )
        response = await self._llm.chat("small", conv)
        parts: list[Any] = [TextPart(content=response.content)]
        for tc in response.tool_calls:
            parts.append(
                ToolCallPart(tool_name=tc.name, args=tc.arguments, tool_call_id=tc.id)
            )
        return PaiModelResponse(parts=parts, model_name=response.model)


class AgentsLiveModel(Model):
    """Modèle OpenAI Agents SDK qui appelle le vrai LLM via le client investia."""

    def __init__(self, llm: Any):
        super().__init__()
        self._llm = llm

    async def get_response(
        self,
        system_instructions: str | None,
        input: Any,
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        **kwargs: Any,
    ) -> ModelResponse:
        messages = _to_messages(input)
        if system_instructions:
            messages.insert(0, {"role": "system", "content": system_instructions})
        response = await self._llm.chat("small", messages)
        output: list[Any] = []
        for tc in response.tool_calls:
            output.append(
                ResponseFunctionToolCall(
                    id=tc.id or "fc_1",
                    call_id=tc.id or "call_1",
                    type="function_call",
                    name=tc.name,
                    arguments=json.dumps(tc.arguments),
                )
            )
        output.append(
            ResponseOutputMessage(
                id="msg_live",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(
                        type="output_text", text=response.content, annotations=[]
                    )
                ],
            )
        )
        return ModelResponse(output=output, usage=Usage(), response_id="resp_live")

    async def stream_response(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError("stream non utilisé dans les evals")
