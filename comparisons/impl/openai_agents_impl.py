"""Implémentation OpenAI Agents SDK (étape 6.2) : Agent + Runner + fake Model."""

import json
import time
from typing import Any

from agents import Agent, FunctionTool, Model, ModelResponse, ModelSettings, Runner
from agents.items import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from agents.usage import Usage

from impl.base import CaseOutcome


class FakeModel(Model):
    """Modèle déterministe : 1er appel = function_call mocké, 2e = réponse finale."""

    def __init__(self, mock_tool_call: dict[str, Any] | None, mock_final: str):
        super().__init__()
        responses = []
        if mock_tool_call:
            responses.append(
                ModelResponse(
                    output=[
                        ResponseFunctionToolCall(
                            id="fc_1",
                            call_id="call_1",
                            type="function_call",
                            name=mock_tool_call["name"],
                            arguments=json.dumps(mock_tool_call.get("arguments", {})),
                        )
                    ],
                    usage=Usage(),
                    response_id="resp_1",
                )
            )
        responses.append(
            ModelResponse(
                output=[
                    ResponseOutputMessage(
                        id="msg_1",
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[
                            ResponseOutputText(
                                type="output_text", text=mock_final, annotations=[]
                            )
                        ],
                    )
                ],
                usage=Usage(),
                response_id="resp_2",
            )
        )
        self._responses = responses

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings: ModelSettings,
        tools,
        output_schema,
        handoffs,
        tracing,
        **kwargs: Any,
    ) -> ModelResponse:
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    async def stream_response(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError("stream non utilisé dans les evals mock")


def _to_function_tool(tool: Any) -> FunctionTool:
    async def on_invoke(ctx: Any, args_json: str) -> str:
        try:
            arguments = json.loads(args_json) if args_json else {}
            args = tool.args_schema.model_validate(arguments)
            result = await tool.run(args)
        except Exception as error:
            # Comme le harness maison : l'erreur est renvoyée au modèle en texte.
            return f"erreur: {error}"
        return json.dumps(result, default=str, ensure_ascii=False)

    return FunctionTool(
        name=tool.name,
        description=tool.description,
        params_json_schema=tool.args_schema.model_json_schema(),
        on_invoke_tool=on_invoke,
    )


async def run_case(
    approach: str,
    case_id: str,
    question: str,
    expected_tool: str,
    mock_tool_call: dict[str, Any],
    mock_final: str,
    tools: dict[str, Any],
) -> CaseOutcome:
    model = FakeModel(mock_tool_call, mock_final)
    agent = Agent(
        name="analyste",
        instructions="Tu es un analyste financier simulé.",
        model=model,
        tools=[_to_function_tool(t) for t in tools.values()],
    )
    t0 = time.perf_counter()
    result = await Runner.run(agent, question)
    duration_ms = (time.perf_counter() - t0) * 1000
    tool_called = None
    for item in result.new_items:
        if getattr(item, "type", None) == "tool_call_item":
            tool_called = getattr(getattr(item, "raw_item", None), "name", None)
            break
    answer = (
        result.final_output
        if isinstance(result.final_output, str)
        else str(result.final_output)
    )
    return CaseOutcome(
        approach=approach,
        case_id=case_id,
        answer=answer,
        tool_called=tool_called,
        tool_ok=tool_called == expected_tool,
        duration_ms=duration_ms,
    )
