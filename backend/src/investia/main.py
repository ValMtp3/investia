"""Point d'entrée de l'API FastAPI."""

import sys

from fastapi import FastAPI
from pydantic import ValidationError

from investia.config import get_settings


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

    app = FastAPI(title="Investia")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Le processus tourne (healthcheck Docker), sans service externe."""
        return {"status": "ok"}

    return app


app = create_app()
