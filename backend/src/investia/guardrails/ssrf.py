"""17g : guard SSRF — bloque les URL qui visent le réseau interne.

Toute URL fournie à un outil (ex. read_pdf) ou reçue d'un pair (callback A2A
futur) passe par `assert_public_http_url` avant le moindre octet réseau :
- scheme http/https uniquement, pas d'userinfo (credentials dans l'URL) ;
- IP littérale → `ipaddress.ip_address(...).is_global` exigé ;
- sinon résolution DNS (`_resolve_host`, factorisée pour les tests) →
  **toutes** les IP résolues doivent être `is_global` (bloque loopback,
  RFC1918, link-local 169.254.0.0/16 dont les métadonnées cloud, reserved,
  multicast, ::1…).

⚠️ DNS rebinding : on vérifie au moment de la résolution, on ne pin pas l'IP
résolue au moment du fetch (nécessiterait un transport httpx custom — piste
notée, hors périmètre 17g). Les redirects doivent être re-vérifiés un par un
par l'appelant (voir tools/pdf.py).
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class SsrfBlockedError(ValueError):
    """L'URL vise une cible non publique (schéma, credentials, IP privée…)."""


async def _resolve_host(host: str) -> list[str]:
    """Résout un host en IP (factorisée pour être mockée dans les tests)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def _require_public_ip(ip: str) -> None:
    """Bloque si `ip` (chaîne déjà résolue) n'est pas une IP publique globale.

    Check explicite (is_global seul laisse passer certains multicast selon les
    versions de Python) : private, loopback, link-local (169.254.x métadonnées
    cloud), multicast, reserved, unspecified.
    """
    addr = ipaddress.ip_address(ip)
    if (
        not addr.is_global
        or addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        raise SsrfBlockedError(f"IP non publique bloquée (SSRF) : {ip}")


def _is_public_ip_literal(host: str) -> bool:
    """True si `host` est une IP littérale publique ; bloque si littérale privée.

    Retourne False si ce n'est pas une IP littérale (→ résolution DNS après).
    """
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    _require_public_ip(host)
    return True


async def assert_public_http_url(url: str) -> str:
    """Valide qu'une URL est http(s) et publique. Lève SsrfBlockedError sinon.

    Retourne l'URL inchangée si OK.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SsrfBlockedError(
            f"schéma non autorisé (http/https uniquement) : {scheme!r}"
        )
    if parsed.username or parsed.password:
        raise SsrfBlockedError("credentials dans l'URL interdits (userinfo)")
    host = parsed.hostname
    if not host:
        raise SsrfBlockedError("URL sans hôte")
    # IP littérale (v4 ou v6 entre crochets) : check direct, pas de DNS
    if _is_public_ip_literal(host):
        return url
    ips = await _resolve_host(host)
    if not ips:
        raise SsrfBlockedError(f"résolution sans IP : {host!r}")
    for ip in ips:
        _require_public_ip(ip)
    return url
