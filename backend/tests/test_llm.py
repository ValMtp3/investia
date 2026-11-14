"""Tests du client LiteLLM, du routeur et du chargement des modèles."""

import json as jsonlib

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
    # 17b : tier small = DeepSeek Flash via LiteLLM
    assert config.small.name == "deepseek/deepseek-flash-latest"
    assert config.large.name == "mistral-large-4"
    assert config.small.price_input_per_m == pytest.approx(0.30)
    assert config.small.price_output_per_m == pytest.approx(1.20)
    assert config.large.price_output_per_m == pytest.approx(4.18)


def test_small_tier_is_deepseek_flash_with_positive_prices():
    small = load_models_config().small
    assert small.name.startswith("deepseek/")
    assert small.price_input_per_m > 0
    assert small.price_output_per_m > 0


def test_models_toml_deepseek_has_cached_input_price_large_does_not():
    # 17f : tarif cache hit DeepSeek (~50x moins cher que le peak)
    config = load_models_config()
    assert config.small.price_input_cached_per_m == pytest.approx(0.006)
    assert config.large.price_input_cached_per_m is None


def test_build_llm_client_uses_settings_budget_per_call():
    # 17f : plafond par appel configurable via env LLM_BUDGET_CENTS_PER_CALL
    from investia.config import Settings
    from investia.llm import build_llm_client

    settings = Settings(
        database_url="postgresql://u:p@localhost/db",
        redis_url="redis://localhost:6379",
        litellm_base_url="http://litellm.test",
        litellm_master_key=SecretStr("sk-test"),
        app_secret_key="x" * 32,
        llm_budget_cents_per_call=5.0,
    )
    client = build_llm_client(settings)
    assert client._budget_cents == 5.0
    # défaut = comportement historique (100 c)
    default_settings = Settings(
        database_url="postgresql://u:p@localhost/db",
        redis_url="redis://localhost:6379",
        litellm_base_url="http://litellm.test",
        litellm_master_key=SecretStr("sk-test"),
        app_secret_key="x" * 32,
    )
    assert build_llm_client(default_settings)._budget_cents == 100.0


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
    assert response.model == "deepseek/deepseek-flash-latest"
    assert response.prompt_tokens == 1000
    assert response.completion_tokens == 100
    # coût = 1000*0.30/1e6 + 100*1.20/1e6 $ = 0.00042 $ = 0.042 centime
    assert response.cost_cents == pytest.approx(0.042, rel=1e-3)


async def test_chat_parses_cached_tokens_and_applies_cached_price():
    # 17f : usage.prompt_tokens_details.cached_tokens (champ standard LiteLLM)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "prompt_tokens_details": {"cached_tokens": 600},
                },
            },
        )

    client = make_client(handler)
    response = await client.chat("small", [{"role": "user", "content": "x"}])
    assert response.cached_tokens == 600
    # 600 cachés à 0.006 $/M + 400 pleins à 0.30 + 100 out à 1.20
    # = (600*0.006 + 400*0.30 + 100*1.20)/1e6 $ = 0.0002436 $ = 0.02436 c
    assert response.cost_cents == pytest.approx(0.02436, rel=1e-3)


async def test_chat_without_cached_details_defaults_to_zero_full_price():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=chat_response("ok", 1000, 100))

    client = make_client(handler)
    response = await client.chat("small", [{"role": "user", "content": "x"}])
    assert response.cached_tokens == 0
    # coût plein = (1000*0.30 + 100*1.20)/1e6 $ = 0.00042 $ = 0.042 c
    assert response.cost_cents == pytest.approx(0.042, rel=1e-3)


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


async def test_chat_with_tools_sends_them_and_parses_tool_calls():
    tool_calls_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_quote",
                                "arguments": '{"symbol": "AAPL"}',
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    tool_spec = {
        "type": "function",
        "function": {
            "name": "get_quote",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = jsonlib.loads(request.content)
        assert body.get("tools") == [tool_spec], (
            "les tools doivent être envoyés au gateway"
        )
        return httpx.Response(200, json=tool_calls_payload)

    client = make_client(handler)
    response = await client.chat(
        "small", [{"role": "user", "content": "prix AAPL ?"}], tools=[tool_spec]
    )
    assert response.tool_calls[0].name == "get_quote"
    assert response.tool_calls[0].arguments == {"symbol": "AAPL"}
    assert response.tool_calls[0].id == "call_1"


# ---------- logprobs (étape 12d : LLM-as-Jev) ----------


def logprobs_payload():
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Non"},
                "logprobs": {
                    "content": [
                        {
                            "token": "Non",
                            "logprob": -0.1,
                            "top_logprobs": [
                                {"token": "Non", "logprob": -0.1},
                                {"token": "Oui", "logprob": -2.3},
                            ],
                        }
                    ]
                },
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 1},
    }


async def test_chat_logprobs_parsed_normalized_and_sent():
    def handler(request: httpx.Request) -> httpx.Response:
        body = jsonlib.loads(request.content)
        assert body.get("logprobs") is True
        assert body.get("top_logprobs") == 5
        return httpx.Response(200, json=logprobs_payload())

    client = make_client(handler)
    response = await client.chat(
        "small", [{"role": "user", "content": "sûr ?"}], logprobs=True
    )
    lp = response.first_token_logprobs
    assert lp is not None
    assert sum(lp.values()) == pytest.approx(1.0)
    assert lp["Non"] > lp["Oui"]
    assert lp["Non"] == pytest.approx(0.9, abs=0.05)


async def test_chat_sans_logprobs_renvoie_none_et_ne_demande_pas():
    def handler(request: httpx.Request) -> httpx.Response:
        body = jsonlib.loads(request.content)
        assert "logprobs" not in body
        return httpx.Response(200, json=chat_response("ok", 10, 5))

    client = make_client(handler)
    response = await client.chat("small", [{"role": "user", "content": "hi"}])
    assert response.first_token_logprobs is None


async def test_chat_logprobs_absents_de_la_reponse_renvoie_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=chat_response("Non", 10, 1))

    client = make_client(handler)
    response = await client.chat(
        "small", [{"role": "user", "content": "sûr ?"}], logprobs=True
    )
    assert response.first_token_logprobs is None
