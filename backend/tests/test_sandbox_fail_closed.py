"""Tests 17c — fail-closed du sandbox run_python : sans binaire d'isolation OS,
le code n'est jamais exécuté (leçon CVE CrewAI-2026-2287) ; pré-vérification
du binaire avant chaque spawn."""

import pytest

from investia.tools.base import ToolError
from investia.tools.python_sandbox import (
    BACKEND_ENV,
    RunPythonArgs,
    RunPythonTool,
    SandboxUnavailableError,
    SubprocessPythonSandbox,
    check_backend_available,
    detect_os_backend,
    fail_closed_enabled,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    monkeypatch.delenv("INVESTIA_SANDBOX_FAIL_CLOSED", raising=False)


def _no_binary(monkeypatch, name="nsjail"):
    monkeypatch.setattr("shutil.which", lambda n: None)


# --- fail_closed_enabled -------------------------------------------------------


def test_fail_closed_on_by_default():
    assert fail_closed_enabled() is True


def test_fail_closed_optout(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_FAIL_CLOSED", "0")
    assert fail_closed_enabled() is False


# --- check_backend_available ----------------------------------------------------


def test_check_raises_when_no_os_binary_and_fail_closed(monkeypatch):
    _no_binary(monkeypatch)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    backend = detect_os_backend()
    assert backend == "subprocess"  # aucun binaire -> repli subprocess
    with pytest.raises(SandboxUnavailableError, match="fail-closed"):
        check_backend_available(backend)


def test_check_passes_when_no_binary_but_fail_closed_off(monkeypatch):
    _no_binary(monkeypatch)
    monkeypatch.setenv("INVESTIA_SANDBOX_FAIL_CLOSED", "0")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    check_backend_available("subprocess")  # opt-out explicite : OK


def test_check_raises_when_forced_backend_binary_missing(monkeypatch):
    monkeypatch.setenv(BACKEND_ENV, "nsjail")
    _no_binary(monkeypatch)
    with pytest.raises(SandboxUnavailableError, match="nsjail"):
        check_backend_available("nsjail")


def test_check_passes_when_binary_present_and_executable(monkeypatch, tmp_path):
    binary = tmp_path / "nsjail"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr(
        "shutil.which", lambda n: str(binary) if n == "nsjail" else None
    )
    check_backend_available("nsjail")  # ne lève pas


def test_check_raises_when_binary_not_executable(monkeypatch, tmp_path):
    binary = tmp_path / "nsjail"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o644)  # présent mais pas exécutable
    monkeypatch.setattr(
        "shutil.which", lambda n: str(binary) if n == "nsjail" else None
    )
    with pytest.raises(SandboxUnavailableError, match="exécutable"):
        check_backend_available("nsjail")


# --- run_code : aucun process spawné sans backend OS (fail-closed) -------------


async def test_run_code_refuses_without_os_backend_and_never_spawns(monkeypatch):
    _no_binary(monkeypatch)
    monkeypatch.setattr("platform.system", lambda: "Linux")

    async def _boom(*a, **k):  # si un process était spawné, le test échouerait
        raise AssertionError("un process a été spawné sans sandbox OS !")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _boom)
    sandbox = SubprocessPythonSandbox()
    with pytest.raises(SandboxUnavailableError, match="fail-closed"):
        await sandbox.run_code("print('ne doit jamais tourner')")


async def test_run_code_works_with_fail_closed_off(monkeypatch):
    # opt-out explicite + backend subprocess forcé = ancien comportement (dev local)
    monkeypatch.setenv("INVESTIA_SANDBOX_FAIL_CLOSED", "0")
    monkeypatch.setenv(BACKEND_ENV, "subprocess")
    sandbox = SubprocessPythonSandbox()
    result = await sandbox.run_code("print(1 + 1)")
    assert result["exit_code"] == 0
    assert "2" in result["stdout"]
    assert result["backend"] == "subprocess"


async def test_run_python_tool_translates_sandbox_unavailable(monkeypatch):
    _no_binary(monkeypatch)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    tool = RunPythonTool(SubprocessPythonSandbox())
    with pytest.raises(ToolError, match="sandbox"):
        await tool.run(RunPythonArgs(code="print('x')"))


async def test_run_code_still_prechecks_before_backend_check(monkeypatch):
    # Le pre-check statique (13c) reste prioritaire : pas de SandboxUnavailableError
    _no_binary(monkeypatch)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    sandbox = SubprocessPythonSandbox()
    result = await sandbox.run_code("eval('1')")  # bloqué par le precheck statique
    assert result["exit_code"] == -1
    assert "precheck" in result


async def test_explicit_subprocess_backend_allowed_with_warning(monkeypatch, caplog):
    """Spec 17c : INVESTIA_SANDBOX_BACKEND=subprocess explicite = choix délibéré
    (ex. CI) -> autorisé même avec fail-closed ON, mais loggé en warning."""
    import logging

    monkeypatch.setenv(BACKEND_ENV, "subprocess")  # fail-closed reste ON (défaut)
    sandbox = SubprocessPythonSandbox()
    with caplog.at_level(logging.WARNING, logger="investia.tools.python_sandbox"):
        result = await sandbox.run_code("print(1 + 1)")
    assert result["exit_code"] == 0
    assert result["backend"] == "subprocess"
    assert any(
        "subprocess" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_check_allows_explicit_subprocess_even_fail_closed(monkeypatch):
    monkeypatch.setenv(BACKEND_ENV, "subprocess")  # fail-closed ON par défaut
    check_backend_available("subprocess")  # ne lève pas
    assert detect_os_backend() == "subprocess"
