"""Tests de l'elicitation MCP (MRTR) sur simulate_order (spec 15a) — TDD avant code.

Contrat : l'outil MCP simulate_order demande une confirmation humaine via
ctx.elicit (form mode). confirm=True → exécution ; declined / cancelled /
confirm=False / client sans support → refus, aucun ordre exécuté (deny-by-default).
"""

import json

import pytest
from fastmcp import Client
from mcp.types import ElicitResult
from test_mcp_server import FakeMarket, FakePortfolio

from investia.mcp_server import build_mcp_server

ORDER = {"symbol": "AAPL", "side": "buy", "quantity": 3}

seen_messages: list[str] = []


async def accept_handler(message, response_type, params, context):
    seen_messages.append(message)
    return {"confirm": True, "note": "vu par le propriétaire"}


async def refuse_handler(message, response_type, params, context):
    seen_messages.append(message)
    return {"confirm": False}


async def decline_handler(message, response_type, params, context):
    seen_messages.append(message)
    return ElicitResult(action="decline")


@pytest.fixture
def portfolio():
    return FakePortfolio()


async def test_confirmed_order_is_executed(portfolio):
    seen_messages.clear()
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp, elicitation_handler=accept_handler) as client:
        result = await client.call_tool("simulate_order", ORDER)
    payload = json.loads(result.content[0].text)
    assert payload["order_id"] == "ord-1"
    assert portfolio.orders == [("AAPL", "buy", 3.0)]
    # le message de confirmation montre les paramètres de l'ordre
    assert seen_messages and "AAPL" in seen_messages[0]
    assert "buy" in seen_messages[0] and "3" in seen_messages[0]


async def test_declined_elicitation_refuses_the_order(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp, elicitation_handler=decline_handler) as client:
        result = await client.call_tool("simulate_order", ORDER, raise_on_error=False)
    assert result.is_error
    assert "non confirmé" in result.content[0].text
    assert portfolio.orders == []


async def test_confirm_false_refuses_the_order(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp, elicitation_handler=refuse_handler) as client:
        result = await client.call_tool("simulate_order", ORDER, raise_on_error=False)
    assert result.is_error
    assert portfolio.orders == []


async def test_client_without_elicitation_support_is_refused(portfolio):
    """Pas de handler côté client → MCPError, aucun ordre (deny-by-default)."""
    from mcp.shared.exceptions import MCPError

    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp) as client:  # pas de handler
        with pytest.raises(MCPError):
            await client.call_tool("simulate_order", ORDER)
    assert portfolio.orders == []


async def test_other_tools_do_not_ask_for_elicitation(portfolio):
    mcp = build_mcp_server(FakeMarket(), portfolio)
    async with Client(mcp) as client:  # pas de handler : get_quote doit passer
        result = await client.call_tool("get_quote", {"symbol": "AAPL"})
    payload = json.loads(result.content[0].text)
    assert payload["value"] == 344.63


# --- 17g : elicitation form-only (jamais de mode "url") -------------------------


def test_form_elicitation_emits_form_mode_only():
    from investia.mcp_server import _form_elicitation

    req = _form_elicitation("Confirmer ?", {"type": "object"})
    assert req.params.mode == "form"


def test_form_elicitation_refuses_url_mode():
    from investia.mcp_server import _form_elicitation

    with pytest.raises(ValueError, match="url"):
        _form_elicitation("Confirmer ?", {"type": "object"}, mode="url")
