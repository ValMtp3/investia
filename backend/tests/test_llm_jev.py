"""Tests du client Jev via LiteLLM (/v1/systemone) — HTTP mocké."""

import json

import httpx
import pytest
from pydantic import SecretStr

from investia.llm.errors import LlmError
from investia.llm.jev import JevClient


def make_client(handler, retry_delay=0.0) -> JevClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JevClient(
        base_url="http://litellm.test",
        master_key=SecretStr("sk-test"),
        http_client=http,
        retry_delay=retry_delay,
    )


SYSTEMONE_RESPONSE = {
    "answers": {
        "q1": {
            "type": "choice",
            "value": "oui",
            "probabilities": {"oui": 0.92, "non": 0.08},
            "confidence": 0.92,
        }
    },
    "usage": {"prompt_tokens": 120, "completion_tokens": 0},
}


async def test_decide_sends_systemone_format_and_parses_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/systemone"
        body = json.loads(request.content)
        assert body["model"] == "jev"
        assert isinstance(body["questions"], dict)
        assert body["questions"]["q1"]["type"] == "choice"
        assert isinstance(body["questions"]["q1"]["criteria"], dict)
        return httpx.Response(200, json=SYSTEMONE_RESPONSE)

    client = make_client(handler)
    answer = await client.decide(
        state={"text": "AAPL monte de 2%"},
        questions={
            "q1": {
                "type": "choice",
                "instructions": "Le marché est haussier ?",
                "criteria": {"oui": "haussier", "non": None},
            }
        },
    )
    assert answer["q1"].value == "oui"
    assert answer["q1"].probabilities == {"oui": 0.92, "non": 0.08}
    assert answer["q1"].confidence == 0.92


async def test_decide_401_raises_llm_error_without_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "Missing API key for Decisions provider 'typesafe'"
                }
            },
        )

    client = make_client(handler)
    with pytest.raises(LlmError, match="401"):
        await client.decide(
            state="x", questions={"q": {"type": "noul", "instructions": "?"}}
        )
    assert calls == 1


async def test_decide_500_retries_twice_then_raises():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = make_client(handler)
    with pytest.raises(LlmError, match="500"):
        await client.decide(
            state="x", questions={"q": {"type": "noul", "instructions": "?"}}
        )
    assert calls == 2
