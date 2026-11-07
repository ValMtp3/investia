"""Cache Redis TTL pour les données de marché.

Redis est une optimisation, pas une dépendance : s'il tombe, on calcule sans cache
(et on le dit dans les logs) au lieu de couper le service.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from investia.cache import get_redis

logger = logging.getLogger(__name__)


async def cached(key: str, ttl: int, factory: Callable[[], Awaitable[Any]]) -> Any:
    """Valeur en cache si présente, sinon calculée via `factory` puis mise en cache.

    `ttl` en secondes. Toute valeur JSON-sérialisable passe (les datetimes
    passent par `default=str` et sont relues avec `from_dict` côté appelant).
    """
    try:
        hit = await get_redis().get(key)
    except Exception:
        logger.warning("Redis indisponible (lecture %s) : calcul sans cache", key)
        hit = None
    if hit is not None:
        return json.loads(hit)
    value = await factory()
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        logger.warning("Redis indisponible (écriture %s) : non mis en cache", key)
    return value


async def is_paused(source: str) -> bool:
    """Vrai si la source est en pause (« trop de requêtes » reçu récemment)."""
    try:
        return await get_redis().get(f"cooldown:{source}") is not None
    except Exception:
        logger.warning("Redis indisponible : pause de %s ignorée", source)
        return False


async def pause(source: str, ttl: int) -> None:
    """Met la source en pause `ttl` secondes : on ne la rappelle pas entre-temps."""
    try:
        await get_redis().set(f"cooldown:{source}", "1", ex=ttl)
    except Exception:
        logger.warning("Redis indisponible : pause de %s non enregistrée", source)


async def remember_failure(key: str, message: str, ttl: int) -> None:
    """Retient un échec `ttl` secondes pour ne pas relancer les mêmes appels."""
    try:
        await get_redis().set(key, message, ex=ttl)
    except Exception:
        logger.warning("Redis indisponible : échec %s non retenu", key)


async def recall_failure(key: str) -> str | None:
    """Message d'un échec retenu récemment, ou None."""
    try:
        raw = await get_redis().get(key)
    except Exception:
        logger.warning("Redis indisponible : échec %s non relu", key)
        return None
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw
