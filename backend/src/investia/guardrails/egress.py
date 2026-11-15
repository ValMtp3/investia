"""23b : egress pinné — anti DNS rebinding (ferme la piste notée en 17g).

À chaque requête, le transport valide l'URL (schéma http/https, pas d'userinfo,
résolution DNS : toutes les IP résolues doivent être globales — cf.
`guardrails/ssrf.py`), puis épingle la connexion TCP à la première IP validée
tout en préservant le `Host` et le SNI d'origine : le certificat TLS est vérifié
sur le nom d'origine, pas sur l'IP.
"""

import httpx

from investia.guardrails import ssrf


class PinnedAsyncTransport(httpx.AsyncBaseTransport):
    """Transport httpx qui épingle chaque connexion à l'IP validée (23b)."""

    def __init__(self) -> None:
        # Le timeout se règle au niveau client (httpx.AsyncClient(timeout=...)).
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        await ssrf.assert_public_http_url(str(url))
        host = url.host
        ips = await ssrf._resolve_host(host)
        if not ips:
            raise ssrf.SsrfBlockedError(f"résolution sans IP : {host!r}")
        for ip in ips:
            ssrf._require_public_ip(ip)
        # Connexion vers l'IP validée, Host + SNI d'origine préservés.
        pinned_url = url.copy_with(host=ips[0])
        default_port = 443 if url.scheme == "https" else 80
        host_header = (
            url.host if url.port in (None, default_port) else f"{url.host}:{url.port}"
        )
        headers = httpx.Headers(request.headers)
        headers["host"] = host_header
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = host
        pinned_request = httpx.Request(
            request.method,
            pinned_url,
            headers=headers,
            content=request.content,
            extensions=extensions,
        )
        return await self._inner.handle_async_request(pinned_request)


def pinned_async_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Client dont chaque connexion est épinglée à l'IP validée (23b).

    `follow_redirects=False` : les redirects sont suivis manuellement par
    l'appelant (ex. tools/pdf.py), re-validés et re-pinnés à chaque saut.
    """
    return httpx.AsyncClient(
        transport=PinnedAsyncTransport(),
        timeout=timeout,
        follow_redirects=False,
    )
