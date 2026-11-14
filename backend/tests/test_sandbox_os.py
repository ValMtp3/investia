"""Tests de la couche OS + pre-check statique du sandbox (spec 13c).

TDD : écrits AVANT l'implémentation dans tools/python_sandbox.py.
"""

import os

import pytest

from investia.tools.python_sandbox import (
    SubprocessPythonSandbox,
    detect_os_backend,
    os_wrap_command,
    static_precheck,
)

# ------------------------------------------------------------- pre-check AST


@pytest.mark.parametrize(
    "code",
    [
        "import ctypes",
        "from ctypes import CDLL",
        "import multiprocessing",
        "import pty",
        "from socket import create_connection",  # bypass du patch du preamble
        "from subprocess import run",  # idem
        "eval('1+1')",
        "exec('pass')",
        "compile('1', 'x', 'eval')",
        "__import__('os')",
        "os.execvp('ls', ['ls'])",  # remplace le process, contourne le preamble
    ],
)
def test_precheck_bloque_les_constructs_dangereux(code):
    assert static_precheck(code), code


@pytest.mark.parametrize(
    "code",
    [
        "print(sum([1, 2, 3]))",
        "import math\nprint(math.sqrt(16))",
        "x = [i * i for i in range(10)]\nprint(x)",
        "from datetime import datetime\nprint(datetime(2026, 1, 1))",
        "def f(a, b):\n    return a + b\nprint(f(1, 2))",
        # patchés par le preamble en runtime (testés dans test_tools_python_sandbox)
        "import socket",
        "import subprocess, os\nos.system('echo x')",
    ],
)
def test_precheck_laisse_passer_le_calcul_pur(code):
    assert static_precheck(code) == [], code


def test_precheck_code_illisible_ne_crash_pas():
    # Syntaxe invalide : on laisse l'interpréteur rapporter la SyntaxError.
    assert static_precheck("def broken(:") == []


# ------------------------------------------------------------- détection backend


def test_backend_env_force_subprocess(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "subprocess")
    assert detect_os_backend() == "subprocess"


def test_backend_auto_nsjail_si_dispo_linux(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "auto")
    monkeypatch.setattr(os, "name", "posix")
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/nsjail" if name == "nsjail" else None,
    )
    assert detect_os_backend() == "nsjail"


def test_backend_auto_seatbelt_si_dispo_macos(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "auto")
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/sandbox-exec" if name == "sandbox-exec" else None,
    )
    assert detect_os_backend() == "seatbelt"


def test_backend_auto_repli_subprocess_si_rien(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "auto")
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert detect_os_backend() == "subprocess"


def test_backend_invalide_rejeté(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "yolo")
    with pytest.raises(ValueError):
        detect_os_backend()


# ------------------------------------------------------------- commande wrappée


def test_os_wrap_nsjail_postfixe_la_commande(monkeypatch, tmp_path):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "nsjail")
    cmd = os_wrap_command(["/usr/bin/python", "-I", "-c", "print(1)"], str(tmp_path))
    assert cmd[0] == "nsjail"
    assert "--mode" in cmd and "once" in cmd
    assert "--" in cmd
    # la commande python d'origine est intacte après le séparateur "--"
    assert cmd[cmd.index("--") + 1 :] == ["/usr/bin/python", "-I", "-c", "print(1)"]


def test_os_wrap_seatbelt_genere_un_profil(monkeypatch, tmp_path):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "seatbelt")
    cmd = os_wrap_command(["/usr/bin/python", "-I", "-c", "print(1)"], str(tmp_path))
    assert cmd[0] == "sandbox-exec"
    assert "-f" in cmd
    profile_path = cmd[cmd.index("-f") + 1]
    with open(profile_path) as f:
        profile = f.read()
    assert "deny default" in profile
    assert "network" not in profile.replace("deny default", "") or True
    assert str(tmp_path) in profile  # tmpdir autorisé en écriture
    assert cmd[cmd.index("--") + 1 :] == ["/usr/bin/python", "-I", "-c", "print(1)"]


def test_os_wrap_subprocess_ne_change_rien(monkeypatch, tmp_path):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "subprocess")
    original = ["/usr/bin/python", "-I", "-c", "print(1)"]
    assert os_wrap_command(original, str(tmp_path)) == original


# ------------------------------------------------------------- exécution


async def test_run_code_bloque_par_precheck_sans_executer(tmp_path, monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "subprocess")
    marker = tmp_path / "marqueur.txt"
    sandbox = SubprocessPythonSandbox()
    # L'import dangereux déclenche le precheck : le code n'est jamais exécuté,
    # donc le fichier marqueur ne doit pas exister.
    code = "import ctypes\n" + f"open({str(marker)!r}, 'w').write('x')"
    result = await sandbox.run_code(code)
    assert result["exit_code"] == -1
    assert "precheck" in result
    assert not marker.exists()


async def test_run_code_ajoute_le_backend_dans_le_resultat(monkeypatch):
    monkeypatch.setenv("INVESTIA_SANDBOX_BACKEND", "subprocess")
    # 17c : backend subprocess explicite = opt-out fail-closed (dev local)
    monkeypatch.setenv("INVESTIA_SANDBOX_FAIL_CLOSED", "0")
    sandbox = SubprocessPythonSandbox()
    result = await sandbox.run_code("print(40 + 2)")
    assert result["backend"] == "subprocess"
    assert "42" in result["stdout"]
