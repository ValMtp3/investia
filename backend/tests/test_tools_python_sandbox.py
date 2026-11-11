"""Tests TDD de la sandbox Python (outil run_python) — sous-process locaux."""

import os
import sys

import pytest
from pydantic import ValidationError

from investia.tools.base import ToolError
from investia.tools.python_sandbox import (
    DEFAULT_MEMORY_BYTES,
    MAX_CODE_CHARS,
    MAX_OUTPUT_CHARS,
    RunPythonArgs,
    RunPythonTool,
    SubprocessPythonSandbox,
)


def make_sandbox(
    timeout: float = 5.0,
    cpu_seconds: int = 5,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
    max_output_chars: int = MAX_OUTPUT_CHARS,
) -> SubprocessPythonSandbox:
    # limites injectables pour des tests rapides
    return SubprocessPythonSandbox(
        timeout=timeout,
        cpu_seconds=cpu_seconds,
        memory_bytes=memory_bytes,
        max_output_chars=max_output_chars,
    )


async def test_print_1plus1_renvoie_stdout_2():
    result = await make_sandbox().run_code("print(1 + 1)")
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "2"
    assert result["stderr"] == ""
    assert result["truncated"] is False


def test_code_trop_long_refuse():
    with pytest.raises(ValidationError):
        RunPythonArgs(code="x" * (MAX_CODE_CHARS + 1))
    with pytest.raises(ValidationError):
        RunPythonArgs(code="")
    assert RunPythonArgs(code="print(1)").code == "print(1)"


async def test_boucle_infinie_timeout_tue_le_process():
    sandbox = make_sandbox(timeout=1.5, cpu_seconds=30)
    with pytest.raises(ToolError, match="timeout"):
        await sandbox.run_code("while True: pass")


async def test_env_ne_contient_pas_les_secrets(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "secret-de-test")
    result = await make_sandbox().run_code(
        "import os\n"
        "print(os.environ.get('BRAVE_API_KEY'))\n"
        "print(os.environ.get('HOME'))\n"
    )
    lines = result["stdout"].strip().splitlines()
    assert lines[0] == "None"  # aucune clé API transmise au fils
    assert lines[1] != os.environ.get("HOME", "")  # HOME = tempdir, pas le vrai


async def test_socket_bloque():
    result = await make_sandbox().run_code(
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('example.com', 80), timeout=2)\n"
        "    print('RESEAU OK')\n"
        "except Exception as e:\n"
        "    print('BLOQUE:', type(e).__name__)\n"
    )
    assert result["exit_code"] == 0
    assert "BLOQUE" in result["stdout"]
    assert "RESEAU OK" not in result["stdout"]


async def test_subprocess_et_os_system_bloques():
    result = await make_sandbox().run_code(
        "import subprocess, os\n"
        "for label, fn in (('subprocess', lambda: subprocess.run(['echo', 'x'])),"
        "                  ('os.system', lambda: os.system('echo x'))):\n"
        "    try:\n"
        "        fn()\n"
        "        print(label, 'OK')\n"
        "    except Exception:\n"
        "        print(label, 'BLOQUE')\n"
    )
    assert result["exit_code"] == 0
    assert result["stdout"].count("BLOQUE") == 2
    assert "OK" not in result["stdout"]


async def test_sortie_tronquee_a_max_output_chars():
    sandbox = make_sandbox(max_output_chars=100)
    result = await sandbox.run_code("print('x' * 10_000)")
    assert len(result["stdout"]) == 100
    assert result["truncated"] is True


async def test_syntax_error_exit_code_non_zero():
    result = await make_sandbox().run_code("def broken(:")
    assert result["exit_code"] != 0
    assert "SyntaxError" in result["stderr"]


async def test_fichier_ecrit_puis_tempdir_supprime():
    result = await make_sandbox().run_code(
        "import pathlib\n"
        "p = pathlib.Path('sortie.txt')\n"
        "p.write_text('data')\n"
        "print(p.resolve())\n"
    )
    path = result["stdout"].strip()
    assert result["exit_code"] == 0
    assert path.endswith("sortie.txt")
    assert not os.path.exists(path)  # tempdir nettoyé après le run


async def test_limite_memoire_non_contournee():
    # RLIMIT_AS n'est pas supporté sur macOS (setrlimit -> EINVAL) : test Linux/VPS only
    if sys.platform == "darwin":
        pytest.skip("RLIMIT_AS non supporté sur macOS")
    # 64 Mo de RAM max pour le fils, le code tente d'allouer ~8 Go
    sandbox = make_sandbox(memory_bytes=64 * 1024 * 1024, timeout=10.0, cpu_seconds=10)
    result = await sandbox.run_code("x = [0] * (1024 * 1024 * 1024)")
    assert result["exit_code"] != 0
    assert "MemoryError" in result["stderr"] or result["exit_code"] == -9


async def test_tool_run_renvoie_source_timestamp_exit_code():
    tool = RunPythonTool(make_sandbox())
    out = await tool.run(RunPythonArgs(code="print(40 + 2)"))
    assert out["stdout"].strip() == "42"
    assert out["exit_code"] == 0
    assert out["source"] == "sandbox"
    assert "timestamp" in out


async def test_sortie_masque_les_secrets_lus_sur_disque(monkeypatch, tmp_path):
    """Même si le code lit un fichier contenant un secret, la sortie est masquée."""
    secret = "sk-test-1234567890abcdef"
    monkeypatch.setenv("BRAVE_API_KEY", secret)
    fichier_secret = tmp_path / "faux.env"
    fichier_secret.write_text(f"BRAVE_API_KEY={secret}\n")
    code = (
        f"from pathlib import Path\nprint(Path({str(fichier_secret)!r}).read_text())\n"
    )
    result = await make_sandbox().run_code(code)
    assert secret not in result["stdout"]
    assert "***" in result["stdout"]
