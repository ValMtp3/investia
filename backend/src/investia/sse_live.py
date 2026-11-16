"""23k : live-attach SSE via Redis pub/sub pour un run encore actif.

En 23f, un client qui renvoie `Last-Event-ID` pour un run `running` recevait les
events stockés puis `detached` (repli en polling). Ici, le serveur s'abonne au
canal `run:<run_id>` publié par le sink et stream les nouveaux events en direct
jusqu'à l'event final. Redis KO -> `LiveAttachUnavailable`, l'appelant retombe
sur `detached` (comportement 23f, zéro régression).
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

# Events qui terminent un run : le live-attach s'arrête après.
FINAL_EVENTS = frozenset({"done", "error"})


class LiveAttachUnavailable(Exception):
    """Redis pub/sub indisponible : l'appelant retombe sur `detached` (23f)."""


def channel_for(run_id: str) -> str:
    return f"run:{run_id}"


async def publish_event(
    client: Any, run_id: str, seq: int, kind: str, payload: dict[str, Any]
) -> None:
    """Publie un event sur `run:<run_id>` — erreur avalée (log warning).

    Le payload est déjà redacté (13a) côté sink ; le canal Redis est interne
    (jamais exposé hors du réseau Docker).
    """
    try:
        await client.publish(
            channel_for(run_id),
            json.dumps(
                {"seq": seq, "event": kind, "payload": payload}, ensure_ascii=False
            ),
        )
    except Exception:
        logger.warning("publish SSE live KO (run %s seq %s)", run_id, seq)


async def live_attach(
    client: Any,
    run_id: str,
    last_seq: int,
    idle_timeout: float = 600.0,
    poll: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    """Yield les events publiés sur `run:<run_id>` avec seq > last_seq (dédup).

    S'arrête sur event final (done/error) ou après `idle_timeout` s de silence.
    Lève LiveAttachUnavailable si l'abonnement échoue.
    """
    channel = channel_for(run_id)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
    except Exception as error:
        raise LiveAttachUnavailable(str(error)) from error
    try:
        idle = 0.0
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=poll
            )
            if message is None:
                idle += poll
                if idle >= idle_timeout:
                    return
                continue
            idle = 0.0
            if message.get("type") != "message":
                continue
            try:
                data = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            seq = int(data.get("seq", 0))
            if seq <= last_seq:
                continue  # déjà rejoué depuis le store (23f)
            last_seq = seq
            event = {
                "seq": seq,
                "event": data.get("event", "message"),
                "payload": data.get("payload", {}),
            }
            yield event
            if event["event"] in FINAL_EVENTS:
                return
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass
