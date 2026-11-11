"""Outil web_search — recherche web (Brave Search API, étape 12f).

Lecture seule. Sans clé BRAVE_API_KEY -> ToolError clair, jamais de contenu inventé.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, SecretStr

from investia.tools.base import BaseTool, ToolError

BRAVE_BASE_URL = "https://api.search.brave.com/res/v1"
MAX_SNIPPET_CHARS = 500


class WebSearcher(Protocol):
    async def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...


class WebSearchArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=300)
    limit: int = Field(5, ge=1, le=10)


class BraveWebSearcher:
    """Client Brave Search API (https://api.search.brave.com/res/v1/web/search)."""

    def __init__(
        self,
        api_key: SecretStr | None,
        base_url: str = BRAVE_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        if self._api_key is None:
            raise ToolError("web_search", "clé manquante : BRAVE_API_KEY non renseignée")
        try:
            response = await self._client.get(
                f"{self._base_url}/web/search",
                params={"q": query, "count": limit},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key.get_secret_value(),
                },
            )
        except httpx.HTTPError as error:
            raise ToolError("web_search", f"erreur réseau Brave : {error}") from error
        if response.status_code != 200:
            raise ToolError(
                "web_search", f"Brave HTTP {response.status_code} (quota ou clé invalide)"
            )
        data = response.json()
        results = (data.get("web") or {}).get("results") or []
        timestamp = datetime.now(UTC).isoformat()
        return [
            {
                "title": str(r.get("title", ""))[:200],
                "url": str(r.get("url", "")),
                "snippet": str(r.get("description", ""))[:MAX_SNIPPET_CHARS],
                "source": "brave",
                "timestamp": timestamp,
            }
            for r in results
        ]


class WebSearchTool(BaseTool[WebSearchArgs]):
    name = "web_search"
    description = (
        "Recherche web générale (actualités, communiqués, sites officiels). "
        "Entrée : query (1-300 car.), limit (1-10 résultats). "
        "Sortie : résultats avec titre, URL, extrait, source et horodatage."
    )
    args_schema = WebSearchArgs

    def __init__(self, searcher: WebSearcher) -> None:
        self._searcher = searcher

    async def run(self, args: WebSearchArgs) -> dict[str, Any]:
        query = args.query.strip()
        if not query:
            raise ToolError(self.name, "query vide")
        try:
            results = await self._searcher.search(query, args.limit)
        except ToolError:
            raise
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {
            "query": query,
            "results": results,
            "source": "brave",
            "timestamp": datetime.now(UTC).isoformat(),
        }
