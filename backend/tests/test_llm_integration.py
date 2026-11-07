"""Test live du client LiteLLM contre le gateway local (:4000)."""

import os

import pytest

from investia.config import Settings
from investia.llm import build_llm_client

pytestmark = pytest.mark.integration

HAS_KEYS = bool(os.environ.get("OPENAI_API_KEY")) and os.environ.get("LITELLM_BASE_URL")


@pytest.mark.skipif(not HAS_KEYS, reason="OPENAI_API_KEY ou LITELLM_BASE_URL manquante")
async def test_live_chat_small_model():
    settings = Settings(_env_file=None)
    client = build_llm_client(settings, budget_cents=50)
    response = await client.chat(
        "small", [{"role": "user", "content": "Réponds exactement: 2+2=?"}]
    )
    assert "4" in response.content
    assert response.prompt_tokens > 0
    assert response.cost_cents >= 0
