"""Implémentation LangGraph (6.2) : create_react_agent + fake model."""

import time
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from impl.base import CaseOutcome


class _FakeChatModel(GenericFakeChatModel):
    """GenericFakeChatModel n'implémente que _generate (sync) : on ajoute _agenerate.

    bind_tools est un no-op : les tool_calls sont déjà dans les messages fake.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_FakeChatModel":
        return self

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _fake_model(mock_tool_call: dict[str, Any] | None, mock_final: str):
    messages = []
    if mock_tool_call:
        messages.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": mock_tool_call["name"],
                        "args": mock_tool_call.get("arguments", {}),
                        "id": "call_1",
                    }
                ],
            )
        )
    messages.append(AIMessage(content=mock_final))
    return _FakeChatModel(messages=iter(messages))


def _to_langchain_tool(tool: Any) -> StructuredTool:
    async def _run(**kwargs: Any) -> str:
        import json

        try:
            args = tool.args_schema.model_validate(kwargs)
            result = await tool.run(args)
        except Exception as error:
            # Comme le harness maison : l'erreur est renvoyée au modèle en texte.
            return f"erreur: {error}"
        return json.dumps(result, default=str, ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=_run,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )


class _LiveChatModel(GenericFakeChatModel):
    """Adapte le vrai client investia (LiteLLM) à l'interface langchain."""

    def __init__(self, llm: Any):
        super().__init__(messages=iter([]))
        self._llm = llm

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_LiveChatModel":
        return self

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import AIMessage as _AIMessage
        from langchain_core.messages import HumanMessage, ToolMessage

        conv = []
        for m in messages:
            if isinstance(m, HumanMessage):
                conv.append({"role": "user", "content": m.content})
            elif isinstance(m, _AIMessage):
                conv.append({"role": "assistant", "content": m.content})
                for tc in getattr(m, "tool_calls", []) or []:
                    conv[-1]["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": str(tc.get("args", {})),
                            },
                        }
                    ]
            elif isinstance(m, ToolMessage):
                conv.append({"role": "tool", "content": m.content})
        response = await self._llm.chat("small", conv)
        msg = _AIMessage(content=response.content)
        if response.tool_calls:
            msg.tool_calls = [
                {
                    "name": c.name,
                    "args": c.arguments,
                    "id": c.id,
                    "type": "tool_call",
                }
                for c in response.tool_calls
            ]
        from langchain_core.outputs import ChatGeneration, ChatResult

        return ChatResult(generations=[ChatGeneration(message=msg)])


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
    model = (
        _LiveChatModel(live_llm)
        if live_llm is not None
        else _fake_model(mock_tool_call, mock_final)
    )
    lc_tools = [_to_langchain_tool(t) for t in tools.values()]
    agent = create_react_agent(model=model, tools=lc_tools)
    t0 = time.perf_counter()
    result = await agent.ainvoke({"messages": [HumanMessage(content=question)]})
    duration_ms = (time.perf_counter() - t0) * 1000
    answer = result["messages"][-1].content
    tool_called = None
    for message in result["messages"]:
        if getattr(message, "tool_calls", None):
            tool_called = message.tool_calls[0]["name"]
            break
    return CaseOutcome(
        approach=approach,
        case_id=case_id,
        answer=answer if isinstance(answer, str) else str(answer),
        tool_called=tool_called,
        tool_ok=tool_called == expected_tool,
        duration_ms=duration_ms,
    )
