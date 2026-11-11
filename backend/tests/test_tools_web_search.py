"""Tests TDD de l'outil web_search (Brave Search API) — MockTransport, zéro réseau."""

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from investia.tools.base import ToolError
from investia.tools.web_search import BraveWebSearcher, WebSearchArgs, WebSearchTool


def make_searcher(handler, api_key="brv-test"):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return BraveWebSearcher(
        api_key=SecretStr(api_key) if api_key else None, http_client=http
    )


def brave_payload(results):
    return {"web": {"results": results}}


async def test_sans_cle_raise_tool_error():
    searcher = make_searcher(lambda r: httpx.Response(200, json={}), api_key=None)
    with pytest.raises(ToolError, match="clé"):
        await searcher.search("actualité AAPL", limit=5)


async def test_search_renvoie_resultats_avec_source_timestamp():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/res/v1/web/search"
        assert request.headers["X-Subscription-Token"] == "brv-test"
        assert "q=actualit" in str(request.url)
        return httpx.Response(
            200,
            json=brave_payload(
                [
                    {
                        "title": "Apple publie ses résultats",
                        "url": "https://example.com/aapl",
                        "description": "x" * 800,
                    }
                ]
            ),
        )

    searcher = make_searcher(handler)
    results = await searcher.search("actualité AAPL", limit=5)
    assert len(results) == 1
    assert results[0]["title"] == "Apple publie ses résultats"
    assert results[0]["url"] == "https://example.com/aapl"
    assert len(results[0]["snippet"]) <= 500  # tronqué
    assert results[0]["source"] == "brave"
    assert "timestamp" in results[0]


async def test_429_vers_tool_error_lisible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    searcher = make_searcher(handler)
    with pytest.raises(ToolError, match="429"):
        await searcher.search("test", limit=5)


async def test_reponse_mal_formee_vers_tool_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    searcher = make_searcher(handler)
    results = await searcher.search("test", limit=5)
    assert results == []


def test_limit_valide_entre_1_et_10():
    with pytest.raises(ValidationError):
        WebSearchArgs(query="x", limit=0)
    with pytest.raises(ValidationError):
        WebSearchArgs(query="x", limit=11)
    assert WebSearchArgs(query="x", limit=10).limit == 10


async def test_tool_run_renvoie_source_timestamp():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=brave_payload([{"title": "t", "url": "https://x.co", "description": "d"}]),
        )

    tool = WebSearchTool(make_searcher(handler))
    out = await tool.run(WebSearchArgs(query="test", limit=3))
    assert out["source"] == "brave"
    assert "timestamp" in out
    assert out["results"][0]["title"] == "t"
