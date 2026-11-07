"""Tests de la base des outils exposés à l'agent."""

import pytest
from pydantic import BaseModel, Field

from investia.tools.base import BaseTool, ToolError


class DummyArgs(BaseModel):
    x: int = Field(..., ge=1)


class DummyTool(BaseTool):
    name = "dummy"
    description = "outil de test"
    args_schema = DummyArgs

    async def run(self, args: DummyArgs) -> dict:
        return {"x": args.x}


async def test_tool_run_returns_dict():
    tool = DummyTool()
    assert await tool.run(DummyArgs(x=2)) == {"x": 2}


def test_tool_openai_format_has_name_description_schema():
    spec = DummyTool().to_openai_tool()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "dummy"
    assert spec["function"]["parameters"]["properties"]["x"]["minimum"] == 1


def test_tool_error_names_the_tool():
    err = ToolError("get_quote", "HTTP 500")
    assert "get_quote" in str(err)
    assert err.tool == "get_quote"


def test_args_validation_rejects_bad_input():
    with pytest.raises(Exception):
        DummyArgs(x=0)
