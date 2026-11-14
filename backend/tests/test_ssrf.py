"""Tests 17g — guard SSRF (assert_public_http_url) : bloque loopback, RFC1918,
link-local (169.254.169.254 = métadonnées cloud), reserved, userinfo, schémas
non-http(s), et les hosts qui résolvent vers une IP privée. Zéro réseau : la
résolution DNS (_resolve_host) est mockée."""

import pytest

from investia.guardrails.ssrf import SsrfBlockedError, assert_public_http_url

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def dns_public(monkeypatch):
    async def _resolve(host: str) -> list[str]:
        return [PUBLIC_IP]

    monkeypatch.setattr("investia.guardrails.ssrf._resolve_host", _resolve)


@pytest.fixture
def dns_private(monkeypatch):
    async def _resolve(host: str) -> list[str]:
        return ["192.168.1.10"]

    monkeypatch.setattr("investia.guardrails.ssrf._resolve_host", _resolve)


async def test_public_https_url_is_accepted(dns_public):
    url = "https://example.com/rapport-annuel.pdf"
    assert await assert_public_http_url(url) == url


async def test_public_literal_ip_is_accepted():
    assert await assert_public_http_url("https://1.1.1.1/x.pdf") == (
        "https://1.1.1.1/x.pdf"
    )


@pytest.mark.parametrize(
    "scheme_url", ["file:///etc/passwd", "ftp://x/y", "gopher://x"]
)
async def test_non_http_schemes_are_rejected(scheme_url):
    with pytest.raises(SsrfBlockedError):
        await assert_public_http_url(scheme_url)


async def test_userinfo_credentials_are_rejected(dns_public):
    with pytest.raises(SsrfBlockedError):
        await assert_public_http_url("https://user:pass@example.com/x.pdf")


async def test_empty_host_is_rejected():
    with pytest.raises(SsrfBlockedError):
        await assert_public_http_url("https://")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/x",
        "http://10.0.0.5/x",
        "http://192.168.1.10/x",
        "http://169.254.169.254/latest/meta-data",  # métadonnées cloud AWS/GCP
        "http://[::1]/x",
        "http://0.0.0.0/x",
        "http://224.0.0.1/x",  # multicast
    ],
)
async def test_private_or_reserved_targets_are_rejected(url, dns_private):
    # dns_private : « localhost » ne fera pas de vraie résolution DNS en test
    with pytest.raises(SsrfBlockedError):
        await assert_public_http_url(url)


async def test_host_resolving_to_private_ip_is_rejected(dns_private):
    with pytest.raises(SsrfBlockedError):
        await assert_public_http_url("https://intranet.example.com/secret.pdf")


async def test_host_with_one_private_ip_among_public_is_rejected(monkeypatch):
    async def _resolve(host: str) -> list[str]:
        return [PUBLIC_IP, "10.1.2.3"]

    monkeypatch.setattr("investia.guardrails.ssrf._resolve_host", _resolve)
    with pytest.raises(SsrfBlockedError):
        await assert_public_http_url("https://mixte.example.com/x.pdf")
