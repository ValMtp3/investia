"""Tests du registre des outils exposés à la boucle d'agent."""

from investia.tools import build_tools


class FakeMarket:
    async def get_quote(self, symbol):
        raise NotImplementedError

    async def get_history(self, symbol, days=30):
        raise NotImplementedError

    async def get_news(self, symbol, limit=5):
        raise NotImplementedError


def test_registry_exposes_the_four_tools():
    tools = build_tools(FakeMarket())
    assert set(tools) == {"get_quote", "get_history", "get_indicators", "get_news"}


def test_every_tool_has_llm_contract():
    for name, tool in build_tools(FakeMarket()).items():
        assert tool.name == name
        assert tool.description, f"{name} sans description"
        assert tool.args_schema.model_json_schema()["type"] == "object"
        spec = tool.to_openai_tool()
        assert spec["function"]["name"] == name
