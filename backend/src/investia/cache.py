"""Connexion Redis async (redis-py)."""

import redis.asyncio as redis

from investia.config import get_settings

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Client Redis async singleton, créé sans se connecter (connexion lazy)."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(
            settings.redis_url.get_secret_value(), decode_responses=True
        )
    return _redis


async def check_redis() -> bool:
    """True si Redis répond (PING), False sinon — sans lever d'exception."""
    try:
        return await get_redis().ping()
    except Exception:
        return False


async def close_redis() -> None:
    """Ferme proprement le client (appelé au shutdown de l'app)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
