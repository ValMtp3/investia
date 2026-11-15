"""Point d'entrée de l'API FastAPI."""

import logging
import re
import secrets
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from investia.cache import check_redis, close_redis
from investia.config import get_settings
from investia.db import check_db, close_db
from investia.market.base import MarketData, MarketDataError, MarketDataService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    yield
    await close_db()
    await close_redis()


class OrderBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    side: str = Field(..., pattern="^(buy|sell)$")
    quantity: float = Field(..., gt=0)


class AdjustBody(BaseModel):
    amount: float
    reason: str = Field(..., min_length=1, max_length=200)


class AgentRunBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    max_turns: int = Field(8, ge=1, le=20)


class ApprovalBody(BaseModel):
    decision: Literal["approved", "refused"]
    # 13d : hash du payload affiché au moment de l'approbation (optionnel,
    # rétrocompatible) ; incohérent avec la demande en attente → 409.
    payload_hash: str | None = None


MARKET_STREAM_INTERVAL = 5.0
# Au plus un tour toutes les secondes : `interval=0` ferait une boucle sans pause.
MARKET_STREAM_MIN_INTERVAL = 1.0
# Chaque symbole peut coûter jusqu'à 4 appels fournisseurs (cascade).
MARKET_STREAM_MAX_SYMBOLS = 20

# Symbole accepté par /market/history : lettres, chiffres et . - ^ =
# (ex. SAP.DE, BTC-USD).
SYMBOL_PATTERN = r"^[A-Za-z0-9.\-^=]{1,20}$"
SYMBOL_RE = re.compile(SYMBOL_PATTERN)
# Mêmes bornes que l'outil `get_history` de l'agent.
HISTORY_MIN_DAYS = 5
HISTORY_MAX_DAYS = 400
# Même valeur que `HISTORY_DAYS` du dashboard (src/api.ts) : le repli du flux de prix
# et le graphique partagent ainsi la même entrée de cache.
HISTORY_DEFAULT_DAYS = 30

# Bornes de la liste des exécutions (GET /traces).
TRACES_DEFAULT_LIMIT = 50
TRACES_MAX_LIMIT = 200

# Bornes de l'historique read-only (GET /orders, GET /portfolio/adjustments, étape 7).
HISTORY_DEFAULT_LIMIT = 50
HISTORY_MAX_LIMIT = 200


async def stream_quote(market: MarketDataService, symbol: str) -> dict[str, Any]:
    """Prix d'un symbole pour le flux ; s'il échoue, sa dernière clôture, étiquetée.

    Repli d'affichage seulement (le dashboard) : `get_quote`, utilisé par l'agent et le
    portefeuille, garde son erreur claire plutôt qu'un prix de la veille. La durée
    (30 jours) est celle du graphique : même entrée de cache, un seul appel
    au fournisseur.
    """
    try:
        quote = (await market.get_quote(symbol)).to_dict()
        quote["symbol"] = symbol
        return quote
    except Exception as error:
        # Le flux d'affichage ne doit jamais s'arrêter pour un symbole : on trace, on
        # tente la dernière clôture, sinon on renvoie l'erreur du prix.
        logger.warning("Prix de %s indisponible : %s", symbol, error)
        try:
            history = await market.get_history(symbol, days=HISTORY_DEFAULT_DAYS)
        except Exception as history_error:
            logger.warning("Clôture de %s indisponible : %s", symbol, history_error)
            history = []
        if not history:
            return {"symbol": symbol, "error": str(error)}
        last_close = max(history, key=lambda point: point.timestamp)
        return {
            **last_close.to_dict(),
            "symbol": symbol,
            "delayed": True,
            "is_close": True,
        }


def daily_closes(history: list[MarketData]) -> list[dict[str, Any]]:
    """Un point `{time, value}` par jour, trié par date. Doublon : le dernier gagne.

    `lightweight-charts` (le graphique du dashboard) refuse deux points à la même date.
    """
    by_day: dict[str, float] = {}
    for point in sorted(history, key=lambda p: p.timestamp):
        by_day[point.timestamp.date().isoformat()] = point.value
    return [{"time": day, "value": value} for day, value in by_day.items()]


def _is_valid_admin_token(provided: str | None, expected: str) -> bool:
    """Compare le jeton admin en temps constant (pas de déduction par le temps)."""
    if not provided:
        return False
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def create_app(
    portfolio_service: Any | None = None,
    llm: Any | None = None,
    market: Any | None = None,
    trace_store: Any | None = None,
    eval_store: Any | None = None,
    approval_registry: Any | None = None,
    backtest_service: Any | None = None,
    memory_store: Any | None = None,
    forecaster: Any | None = None,
) -> FastAPI:
    """Crée l'app. Services injectables (tests) ; sinon construits sur la vraie base.

    Si la configuration est invalide : message clair sur stderr (noms des
    variables manquantes, sans stack trace) puis exit code 1.
    """
    try:
        settings = get_settings()
    except ValidationError as error:
        missing = sorted({str(e["loc"][0]).upper() for e in error.errors() if e["loc"]})
        print(
            "Configuration invalide — variables d'environnement manquantes : "
            + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    # 18a : routeur d'agents A2A appris ; construit plus bas seulement si la
    # vraie base est montée, None sinon (pipeline fixe, zéro régression).
    agent_router = None
    # 12h/23d : routeur de modèle petit/gros, None = règles D44 seules.
    model_router = None
    if market is None or portfolio_service is None:
        from investia.db import get_session
        from investia.evals.store import EvalStore
        from investia.market import build_market_service
        from investia.portfolio import PortfolioService
        from investia.portfolio.backtest_service import BacktestService
        from investia.tracing.otel import init_otel
        from investia.tracing.store import DbTraceStore

        session = get_session()
        market = market or build_market_service(settings)
        portfolio_service = portfolio_service or PortfolioService(session, market)
        backtest_service = backtest_service or BacktestService(session, market)
        trace_store = trace_store or DbTraceStore(session)
        eval_store = eval_store or EvalStore(session)
        if memory_store is None:
            # 16b/16c : mémoire longue (embeddings locaux ou OpenRouter) ;
            # indisponible -> on démarre sans, zéro régression.
            try:
                from investia.memory import build_memory

                memory_store = build_memory(settings)[0]
            except Exception:
                memory_store = None
        # 18a : routeur d'agents A2A appris (k-NN sur agent_feedback) ;
        # indisponible -> pipeline fixe (zéro régression).
        try:
            from investia.agents.router import LearnedAgentRouter
            from investia.agents.router_store import DbAgentFeedback
            from investia.memory import build_memory

            _memory_store, embeddings = build_memory(settings)
            agent_router = LearnedAgentRouter(
                DbAgentFeedback(get_session(), embeddings)
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "routeur d'agents A2A indisponible : pipeline fixe (18a)"
            )
        # 12h/23d : routeur de modèle (knn par défaut ; linucb si ROUTER_MODE=linucb).
        # Indisponible -> None = règles D44 seules (zéro régression).
        try:
            from investia.llm.linucb import LinUCBRouter
            from investia.llm.models import load_models_config
            from investia.llm.router import LearnedRouter
            from investia.llm.router_store import DbLinUCBStore, DbRouterFeedback
            from investia.memory import build_memory

            _memory_store, embeddings = build_memory(settings)
            feedback_store = DbRouterFeedback(get_session(), embeddings)
            if settings.router_mode == "linucb":
                model_router = LinUCBRouter(
                    feedback_store,
                    DbLinUCBStore(get_session()),
                    models=load_models_config(),
                    alpha=settings.router_linucb_alpha,
                    epsilon=settings.router_linucb_epsilon,
                    cost_weight=settings.router_linucb_cost_weight,
                    budget_cents=settings.llm_budget_cents_per_call,
                )
            else:
                model_router = LearnedRouter(feedback_store)
        except Exception:
            logging.getLogger(__name__).warning(
                "routeur de modèle indisponible : règles D44 (12h/23d)"
            )
        forecaster = None
        if settings.mistral_api_key is not None:
            # 17a : prévision Timestral, câblée seulement si la clé est là.
            from investia.market.forecast import MistralTimestralForecaster

            forecaster = MistralTimestralForecaster(
                api_key=settings.mistral_api_key,
                base_url=settings.timestral_base_url,
                model=settings.timestral_model,
            )
        # Spans OTel GenAI exportés vers PostgreSQL (étape 9, D38).
        init_otel(session_factory=session)
    market_service: MarketDataService = market  # non None : construit juste au-dessus
    if llm is None:
        from investia.llm import build_llm_client

        llm = build_llm_client(settings)
    if approval_registry is None:
        from investia.agent.approval import ApprovalRegistry

        approval_registry = ApprovalRegistry()

    # 17e double dial : avertir au démarrage si le sandbox OS est requis mais
    # indisponible (run_python sera retiré pré-schéma par la tool policy).
    if settings.sandbox_mode == "os":
        from investia.tools.policy import any_sandbox_backend_available
        from investia.tools.python_sandbox import fail_closed_enabled

        if fail_closed_enabled() and not any_sandbox_backend_available():
            logging.getLogger(__name__).warning(
                "SANDBOX_MODE=os mais aucun binaire d'isolation "
                "(nsjail/sandbox-exec) : run_python est retiré des outils "
                "envoyés au modèle (fail-closed 17c/17e)."
            )

    # httpx écrit l'URL complète de chaque requête au niveau INFO, donc la clé API
    # des fournisseurs qui la prennent en paramètre (EODHD, Finnhub, CoinGecko).
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Serveur MCP (étape 5.2, D58) : les outils exposés sur /mcp en streamable HTTP.
    from fastmcp.utilities.lifespan import combine_lifespans

    from investia.mcp_server import build_mcp_server

    mcp_server = build_mcp_server(market_service, portfolio_service)
    mcp_app = mcp_server.http_app(path="/")

    app = FastAPI(
        title="Investia", lifespan=combine_lifespans(lifespan, mcp_app.lifespan)
    )
    app.mount("/mcp", mcp_app)

    # Agents A2A (étape 6.1, D60) : 3 sous-apps montées sous /api/agents/<nom>.
    # Les cards annoncent l'URL absolue (base A2A) pour que les clients A2A
    # puissent appeler les agents en HTTP interne.
    from investia.agents import mount_agents
    from investia.agents.executors import (
        AnalysteExecutor,
        RedacteurExecutor,
        RisqueExecutor,
    )
    from investia.agents.orchestrator import default_base_url
    from investia.tools import build_tools as _build_tools

    _tools = _build_tools(market_service, portfolio_service=portfolio_service)
    executors = {
        "analyste": AnalysteExecutor(llm, _tools),
        "risque": RisqueExecutor(),
        "redacteur": RedacteurExecutor(llm, _tools),
    }
    # 15b : signature JWS des Agent Cards si une clé est configurée.
    card_signer = None
    if settings.agent_card_signing_key is not None:
        from investia.agents.cards import make_card_signer

        card_signer = make_card_signer(
            settings.agent_card_signing_key.get_secret_value(),
            kid=settings.agent_card_signing_kid,
            alg=settings.agent_card_signing_alg,
        )
    # 20b : cards enrichies des métriques par agent (feedbacks 18a), servies
    # à la volée ; sans routeur appris, pas de provider = cards statiques 6.1.
    stats_provider = None
    if agent_router is not None:

        async def stats_provider(name: str) -> dict[str, float] | None:
            all_stats = await agent_router.stats()
            return all_stats.get(name)

    mount_agents(
        app,
        executors,
        base_url=default_base_url(),
        card_signer=card_signer,
        stats_provider=stats_provider,
    )
    # Le dashboard en dev tourne sur un autre port : autoriser son origin (navigateur).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Le processus tourne (healthcheck Docker), sans service externe."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        """Prêt si la base et Redis répondent. 503 + détail par service sinon."""
        db_up, redis_up = await check_db(), await check_redis()
        body = {
            "db": "up" if db_up else "down",
            "redis": "up" if redis_up else "down",
        }
        return JSONResponse(body, status_code=200 if db_up and redis_up else 503)

    @app.get("/portfolio")
    async def get_portfolio() -> dict[str, Any]:
        """État du portefeuille simulé, valorisé au dernier prix connu.

        `initial_capital` (ajouté étape 7) = capital de départ après ajustements,
        pour calculer la performance côté dashboard.
        """
        return await portfolio_service.get_portfolio()

    @app.get("/orders")
    async def list_orders(
        limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    ) -> dict[str, Any]:
        """Historique des ordres simulés, du plus récent au plus ancien (read-only)."""
        return {"orders": await portfolio_service.list_orders(limit)}

    @app.get("/portfolio/adjustments")
    async def list_adjustments(
        limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    ) -> dict[str, Any]:
        """Historique des ajustements de capital (read-only, ex. capital initial)."""
        return {"adjustments": await portfolio_service.list_adjustments(limit)}

    def require_backtest_service() -> Any:
        if backtest_service is None:
            raise HTTPException(status_code=503, detail="backtest non configuré")
        return backtest_service

    @app.get("/portfolio/backtest")
    async def get_backtest() -> dict[str, Any]:
        """Backtest du portefeuille simulé vs indice CW8.PA (étape 10, D67).

        Ordres rejoués à la clôture du jour, frais 0,1 %, conversion au taux du
        jour ; résultat caché 24 h en Redis. 503 si l'historique de l'indice
        est indisponible (pas de comparaison possible).
        """
        try:
            return await require_backtest_service().compute()
        except MarketDataError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def require_trace_store() -> Any:
        if trace_store is None:
            raise HTTPException(status_code=503, detail="traces non disponibles")
        return trace_store

    def require_eval_store() -> Any:
        if eval_store is None:
            raise HTTPException(status_code=503, detail="evals non disponibles")
        return eval_store

    @app.get("/traces")
    async def list_traces(
        limit: int = Query(TRACES_DEFAULT_LIMIT, ge=1, le=TRACES_MAX_LIMIT),
    ) -> dict[str, Any]:
        """Exécutions récentes de l'agent, sans la réponse (réservée au détail)."""
        runs = await require_trace_store().list_runs(limit)
        return {"runs": runs}

    @app.get("/traces/{run_id}")
    async def get_trace(run_id: UUID) -> dict[str, Any]:
        """Détail d'une exécution : run complet + étapes pas à pas."""
        data = await require_trace_store().get_run(str(run_id))
        if data.get("run") is None:
            raise HTTPException(status_code=404, detail=f"run inconnu : {run_id}")
        return data

    @app.get("/evals")
    async def list_evals() -> dict[str, Any]:
        """Runs d'evals avec leurs scores, pour les courbes dans le temps."""
        return await require_eval_store().list_eval_runs()

    @app.post("/orders", status_code=200)
    async def place_order(body: OrderBody) -> dict[str, Any]:
        """Ordre simulé (jamais réel) au dernier prix connu + frais 0,1 %."""
        from investia.portfolio import InsufficientFunds

        try:
            return await portfolio_service.place_order(
                body.symbol.strip().upper(), body.side, body.quantity
            )
        except InsufficientFunds as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/portfolio/adjust")
    async def adjust_capital(
        body: AdjustBody, x_admin_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Ajuste le capital (mode admin : jeton exigé en plus d'Authelia, D51)."""
        if not _is_valid_admin_token(
            x_admin_token, settings.app_secret_key.get_secret_value()
        ):
            raise HTTPException(status_code=401, detail="token admin invalide")
        return await portfolio_service.adjust_capital(body.amount, body.reason)

    @app.post("/agent/runs/{run_id}/approval")
    async def respond_approval(run_id: UUID, body: ApprovalBody) -> dict[str, Any]:
        """Décision humaine sur un ordre proposé (D57). 404 si aucune attente,
        409 si déjà décidé. La boucle trace le step « approval » elle-même."""
        key = str(run_id)
        if not approval_registry.has(key):
            raise HTTPException(
                status_code=404, detail=f"aucune approbation en attente pour {run_id}"
            )
        decided = await approval_registry.decide(key, body.decision, body.payload_hash)
        if not decided:
            raise HTTPException(
                status_code=409,
                detail=(
                    "décision déjà enregistrée ou payload_hash incohérent "
                    f"pour {run_id}"
                ),
            )
        return {"status": "ok", "run_id": key, "decision": body.decision}

    @app.post("/agent/run")
    async def agent_run(
        body: AgentRunBody,
        protocol: Literal["legacy", "agui", "a2ui"] = "legacy",
    ) -> Any:
        """Stream SSE de la boucle : start/llm_call/tool_call/guardrail/answer/done
        (+ approval_request/approval pour la validation humaine, D57).

        protocol=legacy (défaut) : `event: <kind>\\ndata: {...}` (rétrocompatible).
        protocol=agui (15c) : blocs `data: {"type": ...}` au format AG-UI."""
        import asyncio

        from fastapi.responses import StreamingResponse

        from investia.agent import run_agent
        from investia.agent.a2ui import A2UIState, format_a2ui_sse
        from investia.agent.agui import RunStateAccumulator, format_agui_sse
        from investia.agent.loop import DEFAULT_APPROVAL_TIMEOUT
        from investia.sse import format_sse
        from investia.tools import build_tools
        from investia.tools.policy import tool_policy_from_settings

        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        # 21a : état partagé — en mode agui, un StateSnapshotEvent après chaque event
        state_acc = RunStateAccumulator() if protocol == "agui" else None
        # 23c : surfaces A2UI actives — en mode a2ui, nettoyées au prochain start
        a2ui_state = A2UIState() if protocol == "a2ui" else None

        async def sink(kind: str, payload: dict[str, Any]) -> None:
            await queue.put((kind, payload))

        def render(kind: str, payload: dict[str, Any]) -> str:
            if protocol == "agui":
                state_event = state_acc.event(kind, payload) if state_acc else None
                return format_agui_sse(kind, payload, state_event=state_event)
            if protocol == "a2ui":
                return format_a2ui_sse(kind, payload, state=a2ui_state)
            return format_sse(kind, payload)

        async def generate():
            task = asyncio.create_task(
                run_agent(
                    body.question,
                    llm,
                    build_tools(
                        market,
                        portfolio_service=portfolio_service,
                        forecaster=forecaster,
                    ),
                    max_turns=body.max_turns,
                    trace_store=trace_store,
                    event_sink=sink,
                    # 17e double dial « quoi » : APPROVAL_MODE=off -> pas de HITL
                    approval_registry=(
                        approval_registry if settings.approval_mode == "order" else None
                    ),
                    context_max_tokens=settings.context_max_tokens or None,
                    keep_last_turns=settings.compaction_keep_last_turns,
                    memory_store=memory_store,
                    router=model_router,  # 12h/23d : None = règles D44
                    # 17e : tool policy pré-schéma (DISABLED_TOOLS + sandbox os KO)
                    tool_policy=tool_policy_from_settings(settings),
                )
            )
            try:
                while True:
                    # Pendant une validation humaine, aucun événement n'est émis
                    # jusqu'à la décision : le timeout d'attente couvre ça.
                    kind, payload = await asyncio.wait_for(
                        queue.get(), timeout=DEFAULT_APPROVAL_TIMEOUT + 30
                    )
                    yield render(kind, payload)
                    if kind == "done":
                        break
            except asyncio.CancelledError:
                task.cancel()
                raise
            except Exception as error:
                yield render("error", {"message": str(error)})
                yield render("done", {"status": "error"})
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/live/llm")
    async def live_llm(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Live check LLM (étape 8) : UN appel minimal sur le modèle le moins cher.

        Protégé par X-Admin-Token (D51) : personne ne déclenche d'appels payants
        sans le jeton. Renvoie ok/ko + modèle + coût + durée, jamais de contenu LLM.
        """
        import time

        if not _is_valid_admin_token(
            x_admin_token, settings.app_secret_key.get_secret_value()
        ):
            raise HTTPException(status_code=401, detail="token admin invalide")
        # Sans clé fournisseur LLM, inutile d'appeler le gateway.
        if not (
            settings.openrouter_api_key or settings.mistral_api_key
        ) and not getattr(settings, "typesafe_api_key", None):
            return {
                "ok": False,
                "error": (
                    "clé LLM manquante (OPENROUTER_API_KEY / MISTRAL_API_KEY dans .env)"
                ),
            }
        start = time.perf_counter()
        try:
            response = await llm.chat(
                "small", [{"role": "user", "content": "Réponds juste OK."}]
            )
        except Exception as error:
            return {"ok": False, "error": str(error)}
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "ok": True,
            "model": response.model,
            "cost_cents": response.cost_cents,
            "duration_ms": round(duration_ms, 1),
        }

    @app.post("/api/agents/run")
    async def agents_run(
        body: AgentRunBody,
        protocol: Literal["legacy", "agui", "a2ui"] = "legacy",
    ) -> Any:
        """Stream SSE du mode multi-agents A2A (6.1) : start/a2a_delegate/.../done.

        protocol=agui (21a) : blocs AG-UI + StateSnapshotEvent (état partagé).
        protocol=a2ui (23c) : blocs `data: {...}` au format A2UI 1.0.
        """
        import asyncio

        from fastapi.responses import StreamingResponse

        from investia.agent.a2ui import A2UIState, format_a2ui_sse
        from investia.agent.agui import RunStateAccumulator, format_agui_sse
        from investia.agent.loop import DEFAULT_APPROVAL_TIMEOUT
        from investia.agents import run_multi_agent
        from investia.sse import format_sse
        from investia.tools import build_tools

        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        state_acc = RunStateAccumulator() if protocol == "agui" else None
        a2ui_state = A2UIState() if protocol == "a2ui" else None

        async def sink(kind: str, payload: dict[str, Any]) -> None:
            await queue.put((kind, payload))

        def render(kind: str, payload: dict[str, Any]) -> str:
            if protocol == "agui":
                state_event = state_acc.event(kind, payload) if state_acc else None
                return format_agui_sse(kind, payload, state_event=state_event)
            if protocol == "a2ui":
                return format_a2ui_sse(kind, payload, state=a2ui_state)
            return format_sse(kind, payload)

        async def generate():
            task = asyncio.create_task(
                run_multi_agent(
                    body.question,
                    llm,
                    build_tools(market, portfolio_service=portfolio_service),
                    trace_store=trace_store,
                    event_sink=sink,
                    router=agent_router,  # 18a : None = pipeline fixe (6.1)
                    forward_agent_events=True,  # 20c : steps des sous-agents en SSE
                )
            )
            try:
                while True:
                    kind, payload = await asyncio.wait_for(
                        queue.get(), timeout=DEFAULT_APPROVAL_TIMEOUT + 30
                    )
                    yield render(kind, payload)
                    if kind == "done":
                        break
            except asyncio.CancelledError:
                task.cancel()
                raise
            except Exception as error:
                yield render("error", {"message": str(error)})
                yield render("done", {"status": "error"})
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/market/stream")
    async def market_stream(
        symbols: str,
        interval: float = Query(MARKET_STREAM_INTERVAL, ge=MARKET_STREAM_MIN_INTERVAL),
        max_events: int | None = None,
    ) -> Any:
        """Stream SSE des prix (toutes les `interval` s, cache Redis 60 s).

        Symboles validés (le symbole finit dans l'URL des fournisseurs) et limités
        en nombre. `max_events` optionnel : arrête après N événements (test/CI).
        """
        import asyncio

        from fastapi.responses import StreamingResponse

        from investia.sse import format_sse

        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not symbol_list:
            raise HTTPException(status_code=422, detail="au moins un symbole")
        if len(symbol_list) > MARKET_STREAM_MAX_SYMBOLS:
            raise HTTPException(
                status_code=422,
                detail=f"{MARKET_STREAM_MAX_SYMBOLS} symboles au maximum",
            )
        invalid = [s for s in symbol_list if not SYMBOL_RE.fullmatch(s)]
        if invalid:
            raise HTTPException(
                status_code=422, detail=f"symbole invalide : {invalid[0][:25]!r}"
            )

        async def generate():
            sent = 0
            try:
                while True:
                    quotes = [
                        await stream_quote(market_service, s) for s in symbol_list
                    ]
                    yield format_sse("quotes", {"quotes": quotes})
                    sent += 1
                    if max_events is not None and sent >= max_events:
                        break
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/market/search")
    async def market_search(
        q: str = Query(..., min_length=2, max_length=30),
        limit: int = Query(10, ge=1, le=20),
    ) -> dict[str, Any]:
        """Recherche de symboles par nom (autocomplétion), multi-sources."""
        search = getattr(market, "search_symbols", None)
        if search is None:
            raise HTTPException(
                status_code=503, detail="recherche non disponible sur ce service"
            )
        try:
            hits = await search(q, limit=limit)
        except MarketDataError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"results": [hit.to_dict() for hit in hits]}

    @app.get("/market/history")
    async def market_history(
        symbol: str = Query(..., pattern=SYMBOL_PATTERN),
        days: int = Query(
            HISTORY_DEFAULT_DAYS, ge=HISTORY_MIN_DAYS, le=HISTORY_MAX_DAYS
        ),
    ) -> dict[str, Any]:
        """Cours de clôture journaliers d'un symbole, pour le graphique du dashboard."""
        symbol = symbol.upper()
        try:
            history = await market.get_history(symbol, days=days)
        except MarketDataError as error:
            # Le message nomme la source (ex. « eodhd: clé API manquante ») sans secret.
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {
            "symbol": symbol,
            "source": history[0].source if history else None,
            "currency": history[0].currency if history else None,
            "delayed": any(point.delayed for point in history),
            "points": daily_closes(history),
        }

    return app


app = create_app()
