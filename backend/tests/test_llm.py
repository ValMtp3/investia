"""Tests du client LiteLLM, du routeur et du chargement des modèles."""

import httpx
import pytest
from pydantic import SecretStr

from investia.llm.client import LlmClient
from investia.llm.errors import LlmError
from investia.llm.models import load_models_config
from investia.llm.router import choose

# ---------- models.toml ----------


def test_models_toml_loads_small_and_large_with_prices():
    config = load_models_config()
    assert config.small.name == "gpt-6-luna"
    assert config.large.name == "mistral-large-4"
    assert config.small.price_input_per_m == pytest.approx(0.10)
    assert config.large.price_output_per_m == pytest.approx(4.18)


# ---------- routeur ----------


def test_router_sends_simple_questions_to_small():
    assert choose("résume cette actualité") == "small"
    assert choose("liste les 3 risques") == "small"


def test_router_sends_deep_analysis_to_large():
    assert choose("analyse AAPL en profondeur") == "large"
    assert choose("donne-moi une stratégie d'investissement") == "large"


def test_router_defaults_short_to_small_long_to_large():
    assert choose("prix de BTC ?") == "small"
    assert choose("x" * 200) == "large"


# ---------- client ----------


def make_client(handler, budget_cents=100, retry_delay=0.0) -> LlmClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LlmClient(
        base_url="http://litellm.test",
        master_key=SecretStr("sk-test"),
        models=load_models_config(),
        budget_cents=budget_cents,
        retry_delay=retry_delay,
        client=http,
    )


def chat_response(content="réponse", prompt=1000, completion=100):
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


async def test_chat_returns_content_usage_and_cost():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json=chat_response("le prix est 344 $", 1000, 100))

    client = make_client(handler)
    response = await client.chat("small", [{"role": "user", "content": "prix AAPL ?"}])
    assert response.content == "le prix est 344 $"
    assert response.model == "gpt-6-luna"
    assert response.prompt_tokens == 1000
    assert response.completion_tokens == 100
    # coût = 1000*0.10/1e6 + 100*0.50/1e6 $ = 0.00015 $ = 0.015 centime
    assert response.cost_cents == pytest.approx(0.015, rel=1e-3)


async def test_budget_exceeded_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=chat_response(prompt=10_000_000, completion=10_000_000)
        )

    client = make_client(handler, budget_cents=1)
    with pytest.raises(LlmError, match="budget"):
        await client.chat("large", [{"role": "user", "content": "analyse"}])


async def test_http_500_retries_then_raises():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = make_client(handler)
    with pytest.raises(LlmError, match="500"):
        await client.chat("small", [{"role": "user", "content": "hi"}])
    assert calls == 2, "2 tentatives max sur 5xx"


async def test_http_401_raises_without_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    client = make_client(handler)
    with pytest.raises(LlmError, match="401"):
        await client.chat("small", [{"role": "user", "content": "hi"}])
    assert calls == 1, "pas de retry sur 401"
