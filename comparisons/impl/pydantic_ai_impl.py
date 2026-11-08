"""Implémentation Pydantic AI (étape 6.2) : Agent + TestModel déterministe."""

import time
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import Tool

from impl.base import CaseOutcome


def _wrap_tool(tool: Any) -> Tool:
    """Convertit un BaseTool investia en Tool pydantic-ai.

    La signature de la fonction est générée (exec) pour que pydantic-ai
    construise le bon schéma JSON depuis les annotations des champs du
    args_schema. takes_ctx=False explicite (nos outils ne prennent pas de
    RunContext).
    """
    fields = tool.args_schema.model_fields

    async def _impl(**kwargs: Any) -> dict[str, Any]:
        try:
            args = tool.args_schema.model_validate(kwargs)
            return await tool.run(args)
        except Exception as error:
            # Comme le harness maison : l'erreur est renvoyée au modèle.
            return {"erreur": str(error)}

    names = list(fields)
    # Annotations résolubles dans le namespace du exec (str, int, Literal[...]...).
    namespace: dict[str, Any] = {"_impl": _impl}
    for n, f in fields.items():
        namespace[f"{n}_t"] = f.annotation
    ann_src = ", ".join(f"{n}: {n}_t" for n in names)
    call_args = ", ".join(f"{n}={n}" for n in names)
    src = f"async def _run({ann_src}):\n    return await _impl({call_args})\n"
    exec(src, namespace)  # noqa: S102 — signature générée depuis les champs pydantic
    fn = namespace["_run"]
    fn.__name__ = tool.name
    fn.__doc__ = tool.description
    return Tool(
        function=fn, name=tool.name, description=tool.description, takes_ctx=False
    )


async def run_case(
    approach: str,
    case_id: str,
    question: str,
    expected_tool: str,
    mock_tool_call: dict[str, Any],
    mock_final: str,
    tools: dict[str, Any],
    live_llm: Any | None = None,
) -> CaseOutcome:
    if live_llm is not None:
        from impl.live_models import PydanticAiLiveModel

        model = PydanticAiLiveModel(live_llm)
    else:
        model = TestModel(
            call_tools=[expected_tool] if expected_tool else [],
            custom_output_text=mock_final,
        )
    agent = Agent(
        model=model,
        system_prompt="Tu es un analyste financier simulé.",
        tools=[_wrap_tool(t) for t in tools.values()],
    )
    t0 = time.perf_counter()
    result = await agent.run(question)
    duration_ms = (time.perf_counter() - t0) * 1000
    tool_called = None
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            if getattr(part, "part_kind", "") == "tool-call":
                tool_called = part.tool_name
                break
        if tool_called:
            break
    return CaseOutcome(
        approach=approach,
        case_id=case_id,
        answer=result.output,
        tool_called=tool_called,
        tool_ok=tool_called == expected_tool,
        duration_ms=duration_ms,
    )
