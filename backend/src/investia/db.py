"""Connexion PostgreSQL async (SQLAlchemy 2.0 + asyncpg).

Le moteur est créé SANS se connecter (la connexion est lazy) : l'app démarre
même si la base est down, c'est `/ready` qui rapporte l'état.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from investia.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Moteur async singleton, créé sans se connecter."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url.get_secret_value())
    return _engine


def get_session() -> async_sessionmaker[AsyncSession]:
    """Fabrique de sessions async."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def check_db() -> bool:
    """True si PostgreSQL répond (SELECT 1), False sinon — sans lever d'exception."""
    try:
        async with get_session()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db() -> None:
    """Ferme proprement le moteur (appelé au shutdown de l'app)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
