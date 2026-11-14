"""Montage des 3 agents A2A dans le backend FastAPI (étape 6.1, D60).

Chaque agent est une sous-application Starlette montée sur /api/agents/<nom> :
- agent card sur /.well-known/agent-card.json
- JSON-RPC sur /jsonrpc

20b : la card peut être reconstruite à chaque GET via `card_factory`
(métriques vivantes, ex. feedbacks 18a) ; une erreur du factory est avalée
et la card statique est servie (jamais de 500).
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCard
from starlette.applications import Starlette
from starlette.routing import BaseRoute

from investia.agents.cards import AGENT_NAMES, build_agent_card

logger = logging.getLogger(__name__)

CARD_URL = "/.well-known/agent-card.json"
RPC_URL = "/jsonrpc"

CardFactory = Callable[[], Awaitable[AgentCard]]
StatsProvider = Callable[[str], Awaitable[dict[str, float] | None]]


def build_agent_subapp(
    card: AgentCard,
    executor: AgentExecutor,
    card_factory: CardFactory | None = None,
) -> Starlette:
    """Sous-app A2A d'un agent : agent card + JSON-RPC, task store en mémoire.

    20b : `card_factory` (optionnel) reconstruit la card à chaque GET de la
    route well-known (via le card_modifier du SDK, ETag/304 conservés) ; une
    erreur est avalée et la card statique est servie.
    """
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    card_modifier = None
    if card_factory is not None:

        async def card_modifier(fallback: AgentCard) -> AgentCard:
            try:
                return await card_factory()
            except Exception:
                logger.exception(
                    "agent card factory: erreur avalée, card statique servie"
                )
                return fallback

    routes: list[BaseRoute] = [
        *create_agent_card_routes(card, card_modifier=card_modifier, card_url=CARD_URL),
        *create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    ]
    return Starlette(routes=routes)


def mount_agents(
    app: Any,
    executors: Mapping[str, AgentExecutor],
    base_url: str = "",
    card_signer: Any | None = None,
    stats_provider: StatsProvider | None = None,
) -> None:
    """Monte les 3 agents sous /api/agents/<nom> dans l'app FastAPI.

    `card_signer` (15b) : si fourni, chaque Agent Card est signée (JWS).
    `stats_provider` (20b) : si fourni, la card de chaque agent est reconstruite
    à chaque GET avec ses métriques (feedbacks 18a) ; sans provider, card
    statique identique à 6.1.
    """
    for name in AGENT_NAMES:
        card = build_agent_card(name, base_url=base_url, signer=card_signer)
        card_factory = None
        if stats_provider is not None:

            async def card_factory(name: str = name) -> AgentCard:
                stats = await stats_provider(name)
                return build_agent_card(
                    name, base_url=base_url, signer=card_signer, stats=stats
                )

        app.mount(
            f"/api/agents/{name}",
            build_agent_subapp(card, executors[name], card_factory=card_factory),
        )
