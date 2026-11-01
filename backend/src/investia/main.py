"""Point d'entrée de l'API FastAPI."""

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from investia.cache import check_redis, close_redis
from investia.config import get_settings
from investia.db import check_db, close_db
from investia.market.base import MarketData, MarketDataError


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


MARKET_STREAM_INTERVAL = 5.0

# Symbole accepté par /market/history : lettres, chiffres et . - ^ =
# (ex. SAP.DE, BTC-USD).
SYMBOL_PATTERN = r"^[A-Za-z0-9.\-^=]{1,20}$"
# Mêmes bornes que l'outil `get_history` de l'agent.
HISTORY_MIN_DAYS = 5
HISTORY_MAX_DAYS = 400
HISTORY_DEFAULT_DAYS = 30


def daily_closes(history: list[MarketData]) -> list[dict[str, Any]]:
    """Un point `{time, value}` par jour, trié par date. Doublon : le dernier gagne.

    `lightweight-charts` (le graphique du dashboard) refuse deux points à la même date.
    """
    by_day: dict[str, float] = {}
    for point in sorted(history, key=lambda p: p.timestamp):
        by_day[point.timestamp.date().isoformat()] = point.value
    return [{"time": day, "value": value} for day, value in by_day.items()]


def create_app(
    portfolio_service: Any | None = None,
    llm: Any | None = None,
    market: Any | None = None,
) -> FastAPI:
    """Crée l'app. `portfolio_service`/`llm`/`market` injectables (tests).

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

    if market is None or portfolio_service is None:
        from investia.db import get_session
        from investia.market import build_market_service
        from investia.portfolio import PortfolioService

        market = market or build_market_service(settings)
        portfolio_service = portfolio_service or PortfolioService(get_session(), market)
    if llm is None:
        from investia.llm import build_llm_client

        llm = build_llm_client(settings)

    app = FastAPI(title="Investia", lifespan=lifespan)
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
        """État du portefeuille simulé, valorisé au dernier prix connu."""
        return await portfolio_service.get_portfolio()

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
        """Ajuste le capital (mode admin, avant Authelia à l'étape 4 bis)."""
        if x_admin_token != settings.app_secret_key.get_secret_value():
            raise HTTPException(status_code=401, detail="token admin invalide")
        return await portfolio_service.adjust_capital(body.amount, body.reason)

    @app.post("/agent/run")
    async def agent_run(body: AgentRunBody) -> Any:
        """Stream SSE de la boucle : start/llm_call/tool_call/guardrail/answer/done."""
        import asyncio

        from fastapi.responses import StreamingResponse

        from investia.agent import run_agent
        from investia.sse import format_sse
        from investia.tools import build_tools

        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        async def sink(kind: str, payload: dict[str, Any]) -> None:
            await queue.put((kind, payload))

        async def generate():
            task = asyncio.create_task(
                run_agent(
                    body.question,
                    llm,
                    build_tools(market),
                    max_turns=body.max_turns,
                    event_sink=sink,
                )
            )
            try:
                while True:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=60)
                    yield format_sse(kind, payload)
                    if kind == "done":
                        break
            except asyncio.CancelledError:
                task.cancel()
                raise
            except Exception as error:
                yield format_sse("error", {"message": str(error)})
                yield format_sse("done", {"status": "error"})
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/market/stream")
    async def market_stream(
        symbols: str,
        interval: float = MARKET_STREAM_INTERVAL,
        max_events: int | None = None,
    ) -> Any:
        """Stream SSE des prix (toutes les `interval` s, cache Redis 60 s).

        `max_events` optionnel : arrête après N événements (utile en test/CI).
        """
        import asyncio

        from fastapi.responses import StreamingResponse

        from investia.sse import format_sse

        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

        async def generate():
            sent = 0
            try:
                while max_events is None or sent < max_events:
                    quotes = []
                    for symbol in symbol_list:
                        try:
                            quote = await market.get_quote(symbol)
                            quote_dict = quote.to_dict()
                            quote_dict["symbol"] = symbol
                            quotes.append(quote_dict)
                        except Exception as error:
                            quotes.append({"symbol": symbol, "error": str(error)})
                    yield format_sse("quotes", {"quotes": quotes})
                    sent += 1
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise

        return StreamingResponse(generate(), media_type="text/event-stream")

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
