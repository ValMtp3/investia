"""Cache Redis TTL générique pour les données de marché."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from investia.cache import get_redis


async def cached(key: str, ttl: int, factory: Callable[[], Awaitable[Any]]) -> Any:
    """Valeur en cache si présente, sinon calculée via `factory` puis mise en cache.

    `ttl` en secondes. Toute valeur JSON-sérialisable passe (les datetimes
    passent par `default=str` et sont relues avec `from_dict` côté appelant).
    """
    redis = get_redis()
    hit = await redis.get(key)
    if hit is not None:
        return json.loads(hit)
    value = await factory()
    await redis.set(key, json.dumps(value, default=str), ex=ttl)
    return value


async def is_paused(source: str) -> bool:
    """Vrai si la source est en pause (« trop de requêtes » reçu récemment)."""
    return await get_redis().get(f"cooldown:{source}") is not None


async def pause(source: str, ttl: int) -> None:
    """Met la source en pause `ttl` secondes : on ne la rappelle pas entre-temps."""
    await get_redis().set(f"cooldown:{source}", "1", ex=ttl)
