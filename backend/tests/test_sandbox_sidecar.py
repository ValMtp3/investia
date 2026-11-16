"""Tests TDD 23i : backend "sidecar" — run_python délégué au sidecar Go (unix socket).

Fail-closed : sans socket, aucune exécution. Le pre-check statique 13c reste
appliqué côté Python avant tout envoi au sidecar.
"""

import json
import tempfile
from pathlib import Path

import pytest
from aiohttp import web

from investia.tools.base import ToolError
from investia.tools.python_sandbox import (
    BACKEND_ENV,
    SIDECAR_SOCK_ENV,
    RunPythonTool,
    SandboxUnavailableError,
    SidecarSandbox,
    detect_os_backend,
)


def short_sock() -> Path:
    """Socket dans un chemin court (macOS limite AF_UNIX à ~104 car.)."""
    return Path(tempfile.mkdtemp(dir="/tmp", prefix="isb-")) / "sandbox.sock"


async def start_fake_sidecar(sock_path: Path, handler) -> web.AppRunner:
    """Petit serveur HTTP de test sur unix socket, comme le sidecar Go."""
    app = web.Application()
    app.router.add_post("/run", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.UnixSite(runner, str(sock_path))
    await site.start()
    return runner


async def ok_handler(request: web.Request) -> web.Response:
    body = await request.json()
    assert "code" in body and "timeout_s" in body
    return web.json_response(
        {
            "exit_code": 0,
            "stdout": f"ran: {body['code'][:20]}",
            "stderr": "",
            "truncated": False,
            "backend": "sidecar-go",
        }
    )


def test_detect_os_backend_sidecar_explicit(monkeypatch):
    monkeypatch.setenv(BACKEND_ENV, "sidecar")
    assert detect_os_backend() == "sidecar"


def test_detect_os_backend_invalid(monkeypatch):
    monkeypatch.setenv(BACKEND_ENV, "nope")
    with pytest.raises(ValueError, match="INVESTIA_SANDBOX_BACKEND"):
        detect_os_backend()


def test_detect_os_backend_auto_detects_socket(monkeypatch, tmp_path):
    sock = short_sock()
    sock.write_text("")  # le socket existe -> sidecar dispo
    monkeypatch.setenv(BACKEND_ENV, "auto")
    monkeypatch.setenv(SIDECAR_SOCK_ENV, str(sock))
    assert detect_os_backend() == "sidecar"


async def test_sidecar_run_code_ok(tmp_path):
    sock = short_sock()
    runner = await start_fake_sidecar(sock, ok_handler)
    try:
        sandbox = SidecarSandbox(sock_path=sock)
        result = await sandbox.run_code("print('hello')")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]
        assert result["backend"] == "sidecar-go"
        assert result["truncated"] is False
    finally:
        await runner.cleanup()


async def test_sidecar_fail_closed_without_socket(tmp_path):
    sandbox = SidecarSandbox(sock_path=tmp_path / "absent.sock")
    with pytest.raises(SandboxUnavailableError, match="socket"):
        await sandbox.run_code("print(1)")


async def test_sidecar_fail_closed_on_503(tmp_path):
    async def ko_handler(request: web.Request) -> web.Response:
        return web.json_response({"error": "landlock indisponible"}, status=503)

    sock = short_sock()
    runner = await start_fake_sidecar(sock, ko_handler)
    try:
        sandbox = SidecarSandbox(sock_path=sock)
        with pytest.raises(SandboxUnavailableError, match="503|indisponible"):
            await sandbox.run_code("print(1)")
    finally:
        await runner.cleanup()


async def test_precheck_applies_before_sending(tmp_path):
    """Un code dangereux n'est jamais envoyé au sidecar (compteur de requêtes)."""
    calls = 0

    async def counting_handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return await ok_handler(request)

    sock = short_sock()
    runner = await start_fake_sidecar(sock, counting_handler)
    try:
        sandbox = SidecarSandbox(sock_path=sock)
        result = await sandbox.run_code("import ctypes")
        assert result["exit_code"] == -1
        assert result["precheck"]
        assert calls == 0  # rien n'a été envoyé au sidecar
    finally:
        await runner.cleanup()


async def test_secrets_redacted_in_sidecar_output(tmp_path, monkeypatch):
    secret = "supersecretvalue123"
    monkeypatch.setenv("INVESTIA_TEST_API_KEY", secret)

    async def leaky_handler(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "exit_code": 0,
                "stdout": f"leak: {secret}",
                "stderr": "",
                "truncated": False,
                "backend": "sidecar-go",
            }
        )

    sock = short_sock()
    runner = await start_fake_sidecar(sock, leaky_handler)
    try:
        sandbox = SidecarSandbox(sock_path=sock)
        result = await sandbox.run_code("print(1)")
        assert secret not in result["stdout"]
        assert "***REDACTE***" in result["stdout"]
    finally:
        await runner.cleanup()


async def test_run_python_tool_over_sidecar(tmp_path):
    sock = short_sock()
    runner = await start_fake_sidecar(sock, ok_handler)
    try:
        tool = RunPythonTool(SidecarSandbox(sock_path=sock))
        from investia.tools.python_sandbox import RunPythonArgs

        out = await tool.run(RunPythonArgs(code="print('42')"))
        assert out["exit_code"] == 0
        assert out["source"] == "sandbox"
        assert "timestamp" in out
    finally:
        await runner.cleanup()


async def test_run_python_tool_fail_closed_message(tmp_path):
    tool = RunPythonTool(SidecarSandbox(sock_path=tmp_path / "absent.sock"))
    from investia.tools.python_sandbox import RunPythonArgs

    with pytest.raises(ToolError, match="indisponible|refusée"):
        await tool.run(RunPythonArgs(code="print(1)"))


async def test_sidecar_client_timeout(tmp_path):
    """Le sidecar met trop de temps -> ToolError, pas d'exécution infinie."""

    async def slow_handler(request: web.Request) -> web.Response:
        import asyncio

        await asyncio.sleep(5)
        return await ok_handler(request)

    sock = short_sock()
    runner = await start_fake_sidecar(sock, slow_handler)
    try:
        sandbox = SidecarSandbox(sock_path=sock, timeout=0.2, client_timeout=0.5)
        with pytest.raises(SandboxUnavailableError, match="timeout|délai"):
            await sandbox.run_code("print(1)")
    finally:
        await runner.cleanup()


def test_policy_counts_sidecar_as_available(monkeypatch, tmp_path):
    """any_sandbox_backend_available voit le sidecar si son socket existe."""
    from investia.tools.policy import any_sandbox_backend_available

    sock = short_sock()
    sock.write_text("")
    monkeypatch.setenv(BACKEND_ENV, "sidecar")
    monkeypatch.setenv(SIDECAR_SOCK_ENV, str(sock))
    assert any_sandbox_backend_available() is True


def test_payload_is_json_over_unix_socket(tmp_path):
    """Contrat : POST /run en JSON sur le socket (vu par le handler de test)."""

    seen: list[str] = []

    async def capture_handler(request: web.Request) -> web.Response:
        body = await request.json()
        seen.append(json.dumps(body, sort_keys=True))
        return await ok_handler(request)

    async def main_test():
        sock = short_sock()
        runner = await start_fake_sidecar(sock, capture_handler)
        try:
            sandbox = SidecarSandbox(sock_path=sock, timeout=3.0)
            await sandbox.run_code("print('contrat')")
            seen_body = json.loads(seen[0])
            assert seen_body["code"] == "print('contrat')"
            assert seen_body["timeout_s"] == 3.0
            assert "max_output_chars" in seen_body
        finally:
            await runner.cleanup()

    import asyncio

    asyncio.run(main_test())
