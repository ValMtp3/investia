"""Montage des 3 agents A2A dans le backend FastAPI (étape 6.1, D60).

Chaque agent est une sous-application Starlette montée sur /api/agents/<nom> :
- agent card sur /.well-known/agent-card.json
- JSON-RPC sur /jsonrpc
"""

from collections.abc import Mapping
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCard
from starlette.applications import Starlette
from starlette.routing import BaseRoute

from investia.agents.cards import AGENT_NAMES, build_agent_card

CARD_URL = "/.well-known/agent-card.json"
RPC_URL = "/jsonrpc"


def build_agent_subapp(card: AgentCard, executor: AgentExecutor) -> Starlette:
    """Sous-app A2A d'un agent : agent card + JSON-RPC, task store en mémoire."""
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes: list[BaseRoute] = [
        *create_agent_card_routes(card, card_url=CARD_URL),
        *create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    ]
    return Starlette(routes=routes)


def mount_agents(
    app: Any, executors: Mapping[str, AgentExecutor], base_url: str = ""
) -> None:
    """Monte les 3 agents sous /api/agents/<nom> dans l'app FastAPI."""
    for name in AGENT_NAMES:
        card = build_agent_card(name, base_url=base_url)
        app.mount(f"/api/agents/{name}", build_agent_subapp(card, executors[name]))
