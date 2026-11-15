"""Tests 23b — egress pinné : la connexion TCP vise l'IP validée à ce moment,
Host + SNI d'origine préservés (anti DNS rebinding, ferme la piste notée en 17g).

TDD : écrits AVANT backend/src/investia/guardrails/egress.py.
Aucun réseau : le transport interne est mocké, la résolution DNS aussi.
"""

import httpx
import pytest

from investia.guardrails import egress, ssrf


def _install_fakes(monkeypatch, captured, ips):
    class FakeInner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            captured.append(request)
            return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kw: FakeInner())

    async def fake_resolve(host):
        return list(ips)

    monkeypatch.setattr(ssrf, "_resolve_host", fake_resolve)


async def test_pinned_client_connecte_sur_ip_validee(monkeypatch):
    captured = []
    _install_fakes(monkeypatch, captured, ["93.184.216.34"])
    client = egress.pinned_async_client()
    response = await client.get("https://example.com/doc.pdf")
    assert response.status_code == 200
    assert len(captured) == 1
    req = captured[0]
    # connexion épinglée à l'IP validée…
    assert req.url.host == "93.184.216.34"
    assert req.url.scheme == "https"
    # …mais Host et SNI d'origine (le certificat est vérifié sur example.com)
    assert req.headers["host"] == "example.com"
    assert req.extensions.get("sni_hostname") == "example.com"


async def test_port_conserve_dans_le_host(monkeypatch):
    captured = []
    _install_fakes(monkeypatch, captured, ["93.184.216.34"])
    client = egress.pinned_async_client()
    await client.get("https://example.com:8443/x")
    req = captured[0]
    assert req.url.port == 8443
    assert req.headers["host"] == "example.com:8443"
    assert req.extensions.get("sni_hostname") == "example.com"


async def test_resolution_privee_bloquee_avant_connexion(monkeypatch):
    captured = []
    _install_fakes(monkeypatch, captured, ["10.0.0.5"])
    client = egress.pinned_async_client()
    with pytest.raises(ssrf.SsrfBlockedError):
        await client.get("https://interne.local/x")
    assert captured == []  # aucune connexion ouverte


async def test_une_ip_privee_parmi_publiques_bloquee(monkeypatch):
    captured = []
    _install_fakes(monkeypatch, captured, ["93.184.216.34", "192.168.1.1"])
    client = egress.pinned_async_client()
    with pytest.raises(ssrf.SsrfBlockedError):
        await client.get("https://example.com/x")
    assert captured == []


async def test_scheme_non_http_rejete(monkeypatch):
    captured = []
    _install_fakes(monkeypatch, captured, ["93.184.216.34"])
    client = egress.pinned_async_client()
    with pytest.raises(ssrf.SsrfBlockedError):
        await client.get("ftp://example.com/x")
    assert captured == []


async def test_rebinding_relecture_dns_reste_bloquee(monkeypatch):
    """Le DNS est re-résolu à chaque requête : un host redevenu privé est bloqué."""
    captured = []
    state = {"ips": ["93.184.216.34"]}

    class FakeInner(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            captured.append(request)
            return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kw: FakeInner())

    async def fake_resolve(host):
        return list(state["ips"])

    monkeypatch.setattr(ssrf, "_resolve_host", fake_resolve)
    client = egress.pinned_async_client()
    await client.get("https://example.com/x")
    state["ips"] = ["169.254.169.254"]  # rebinding : métadonnées cloud
    with pytest.raises(ssrf.SsrfBlockedError):
        await client.get("https://example.com/x")
    assert len(captured) == 1  # seule la première requête a connecté
