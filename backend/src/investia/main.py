"""Point d'entrée de l'API FastAPI."""

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from investia.cache import check_redis, close_redis
from investia.config import get_settings
from investia.db import check_db, close_db


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


def create_app(portfolio_service: Any | None = None) -> FastAPI:
    """Crée l'application. `portfolio_service` injectable pour les tests.

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

    if portfolio_service is None:
        from investia.db import get_session
        from investia.market import build_market_service
        from investia.portfolio import PortfolioService

        portfolio_service = PortfolioService(
            get_session(), build_market_service(settings)
        )

    app = FastAPI(title="Investia", lifespan=lifespan)

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

    return app


app = create_app()
