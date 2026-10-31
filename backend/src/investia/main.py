"""Point d'entrée de l'API FastAPI."""

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from investia.cache import check_redis, close_redis
from investia.config import get_settings
from investia.db import check_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    yield
    await close_db()
    await close_redis()


def create_app() -> FastAPI:
    """Crée l'application.

    Si la configuration est invalide : message clair sur stderr (noms des
    variables manquantes, sans stack trace) puis exit code 1.
    """
    try:
        get_settings()
    except ValidationError as error:
        missing = sorted({str(e["loc"][0]).upper() for e in error.errors() if e["loc"]})
        print(
            "Configuration invalide — variables d'environnement manquantes : "
            + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

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

    return app


app = create_app()
