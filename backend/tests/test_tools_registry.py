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


class FakeSearcher:
    async def search(self, query, limit):
        return []


class FakePdfReader:
    async def extract_text(self, url, max_pages):
        return ""


def test_web_and_pdf_tools_added_when_services_provided():
    tools = build_tools(
        FakeMarket(), web_searcher=FakeSearcher(), pdf_reader=FakePdfReader()
    )
    assert {"web_search", "read_pdf"} <= set(tools)
    assert len(tools) == 6


def test_registry_retrocompatible_sans_services_web_pdf():
    tools = build_tools(FakeMarket())
    assert "web_search" not in tools
    assert "read_pdf" not in tools


def test_system_prompt_cite_web_search_et_read_pdf():
    from investia.agent.prompts import SYSTEM_PROMPT

    assert "web_search" in SYSTEM_PROMPT
    assert "read_pdf" in SYSTEM_PROMPT


def test_memory_tools_added_when_store_available():
    from investia.memory.embeddings import FakeEmbeddingsForTests

    class FakeStore:
        async def save(self, content, embedding=None):
            return "mem-1"

        async def recall(self, query, k=5):
            return []

    tools = build_tools(
        FakeMarket(), memory_store=FakeStore(), embeddings=FakeEmbeddingsForTests()
    )
    assert {"save_memory", "recall_memory"} <= set(tools)
    assert len(tools) == 6
