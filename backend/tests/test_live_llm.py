"""Tests de GET /api/live/llm (spec 8) : live check LLM, protégé par X-Admin-Token.

Contrat : 401 sans/mauvais token ; 200 {ok:true, model, cost_cents, duration_ms}
avec LLM fake ; 200 {ok:false, error} si le LLM échoue ; ok:false « clé manquante »
si aucune clé LLM configurée (pas d'exception, pas de 500).
"""

import httpx

from investia.llm.client import LlmResponse
from investia.main import create_app

ADMIN = "test-admin-secret-0123456789abcdef"


class FakeLlmOk:
    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        assert model_key == "small"  # le live check utilise le modèle le moins cher
        return LlmResponse(
            content="ok",
            model="gpt-6-luna",
            prompt_tokens=5,
            completion_tokens=2,
            cost_cents=0.001,
        )


class FakeLlmKo:
    async def chat(self, model_key, messages, temperature=0.2, tools=None, logprobs=False):
        raise RuntimeError("gateway down")


class FakeMarket:
    async def get_quote(self, symbol):
        raise NotImplementedError

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


class FakePortfolio:
    async def get_portfolio(self):
        return {}

    async def place_order(self, *a):
        return {}

    async def adjust_capital(self, *a):
        return {}


class FakeTrace:
    async def list_runs(self, limit=50):
        return []

    async def get_run(self, rid):
        return {"run": None, "steps": []}


def make_app(monkeypatch, llm, with_provider_key: bool = True) -> "httpx.AsyncClient":
    for var in ("DATABASE_URL", "REDIS_URL", "LITELLM_BASE_URL", "LITELLM_MASTER_KEY"):
        monkeypatch.setenv(
            var,
            {
                "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "LITELLM_BASE_URL": "http://localhost:4000",
                "LITELLM_MASTER_KEY": "sk-test",
            }[var],
        )
    monkeypatch.setenv("APP_SECRET_KEY", ADMIN)
    if with_provider_key:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    app = create_app(
        portfolio_service=FakePortfolio(),
        llm=llm,
        market=FakeMarket(),
        trace_store=FakeTrace(),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_live_llm_requires_admin_token(monkeypatch):
    async with make_app(monkeypatch, FakeLlmOk()) as client:
        assert (await client.get("/api/live/llm")).status_code == 401
        assert (
            await client.get("/api/live/llm", headers={"X-Admin-Token": "mauvais"})
        ).status_code == 401


async def test_live_llm_ok_returns_model_cost_duration(monkeypatch):
    async with make_app(monkeypatch, FakeLlmOk()) as client:
        resp = await client.get("/api/live/llm", headers={"X-Admin-Token": ADMIN})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["model"] == "gpt-6-luna"
        assert body["cost_cents"] == 0.001
        assert body["duration_ms"] >= 0
        assert "error" not in body
        # le contenu LLM ne fuite pas dans la réponse
        assert "ok" != body.get("content")


async def test_live_llm_gateway_error_is_ok_false_not_500(monkeypatch):
    async with make_app(monkeypatch, FakeLlmKo()) as client:
        resp = await client.get("/api/live/llm", headers={"X-Admin-Token": ADMIN})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "gateway down" in body["error"]


async def test_live_llm_missing_provider_key_is_ok_false(monkeypatch):
    """Sans clé fournisseur : ok:false « clé manquante », pas d'appel."""
    async with make_app(monkeypatch, FakeLlmOk(), with_provider_key=False) as client:
        resp = await client.get("/api/live/llm", headers={"X-Admin-Token": ADMIN})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "clé" in body["error"].lower() or "key" in body["error"].lower()
