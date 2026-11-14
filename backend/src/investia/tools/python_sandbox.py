"""Outil run_python — exécution de code Python dans un sous-process isolé (étape 12g).

Menace : code généré par le LLM de l'agent (maladresse : boucle infinie, écriture
massive, fork, fuite de secrets), pas un attaquant externe. Isolation, zéro dépendance :
tempdir dédié supprimé après le run, env whitelist (aucun secret), `python -I`,
limites `resource` (CPU/RAM/fichiers) posées dans le preamble, réseau et sous-process
bloqués (best effort, patch de socket/subprocess/os.system), timeout avec kill du
groupe de processus. Sans isolation noyau (macOS) : documenté dans la spec 12g.
"""

import ast
import asyncio
import os
import platform
import re
import shutil
import signal
import sys
import tempfile
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from investia.tools.base import BaseTool, ToolError

MAX_CODE_CHARS = 10_000
MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 10.0
DEFAULT_CPU_SECONDS = 10
DEFAULT_MEMORY_BYTES = 512 * 1024 * 1024  # 512 Mo
DEFAULT_MAX_OPEN_FILES = 64
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 Mo

SECRET_NAME_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
MIN_SECRET_LEN = 8
REDACTED = "***REDACTE***"


def _secret_values() -> list[str]:
    """Valeurs des variables d'env du parent ressemblant à des secrets."""
    return [
        value
        for name, value in os.environ.items()
        if SECRET_NAME_RE.search(name) and len(value) >= MIN_SECRET_LEN
    ]


def _redact(text: str, secrets: list[str]) -> str:
    """Masque les secrets dans la sortie (le fils peut lire le disque : .env, etc.)."""
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text


# ------------------------------------------------- 13c : pre-check + couche OS

# 13c : pre-check statique. Le preamble patch déjà socket/subprocess/os.system
# en runtime (testé), donc un `import socket` simple passe — mais ctypes/libc
# contourne tout, et `from socket import X` contourne le patch du module.
HARD_BLOCKED_MODULES = frozenset({"ctypes", "multiprocessing", "importlib", "pty"})
# Le `from X import ...` bypass le patch d'attributs du preamble : toujours bloqué.
FROM_IMPORT_BLOCKED_MODULES = HARD_BLOCKED_MODULES | {"socket", "subprocess"}
DANGEROUS_CALLS = frozenset({"eval", "exec", "compile", "__import__"})
# os.system/os.popen sont patchés par le preamble (laissés passer, testés) ;
# les exec*/spawn* remplacent le process et contournent le preamble : bloqués.
DANGEROUS_OS_ATTRS = frozenset(
    {
        "execv",
        "execvp",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "spawnv",
        "spawnve",
        "spawnl",
        "spawnle",
    }
)

BACKEND_ENV = "INVESTIA_SANDBOX_BACKEND"
VALID_BACKENDS = frozenset({"nsjail", "seatbelt", "subprocess"})


def static_precheck(code: str) -> list[str]:
    """Analyse AST stdlib du code utilisateur : retourne la liste des problèmes.

    Liste non vide = le code ne doit PAS être exécuté. Zéro dépendance.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Laisse l'interpréteur rapporter la SyntaxError (comportement 12g).
        return []
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in HARD_BLOCKED_MODULES:
                    issues.append(f"import interdit : {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FROM_IMPORT_BLOCKED_MODULES:
                issues.append(f"import interdit : from {node.module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DANGEROUS_CALLS:
                issues.append(f"appel interdit : {func.id}()")
            elif (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr in DANGEROUS_OS_ATTRS
            ):
                issues.append(f"appel interdit : os.{func.attr}()")
    return issues


def detect_os_backend() -> str:
    """Backend d'isolation OS : env INVESTIA_SANDBOX_BACKEND, défaut auto.

    auto = nsjail si dispo (Linux), sandbox-exec/Seatbelt si dispo (macOS),
    sinon repli sur le sous-processus seul.
    """
    choice = os.environ.get(BACKEND_ENV, "auto")
    if choice != "auto":
        if choice not in VALID_BACKENDS:
            raise ValueError(
                f"{BACKEND_ENV} inconnu : {choice!r} "
                f"(attendu : auto | {' | '.join(sorted(VALID_BACKENDS))})"
            )
        return choice
    if platform.system() == "Linux" and shutil.which("nsjail"):
        return "nsjail"
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    return "subprocess"


def _seatbelt_profile(workdir: str) -> str:
    """Profil Seatbelt : deny default, lecture FS libre, écriture tmpdir seul.

    realpath : sur macOS /tmp et /var sont des symlinks vers /private/..., et
    Seatbelt compare les chemins résolus.
    """
    real = os.path.realpath(workdir)
    return (
        "(version 1)\n"
        "(deny default)\n"
        "(allow file-read*)\n"
        f'(allow file-write* (subpath "{real}"))\n'
        "(allow process-exec)\n"
        "(allow process-fork)\n"
        "(allow sysctl-read)\n"
        "(allow mach-lookup)\n"
        "(allow signal (target self))\n"
    )


def os_wrap_command(cmd: list[str], workdir: str) -> list[str]:
    """Enveloppe la commande python d'une couche OS (nsjail / Seatbelt).

    nsjail clone par défaut de nouveaux namespaces (user, net isolé loopback
    uniquement, pid, mount) + rlimits par process. Seatbelt applique le profil
    deny-default. Sans binaire disponible : commande inchangée (repli).
    """
    backend = detect_os_backend()
    if backend == "nsjail":
        return [
            "nsjail",
            "--mode",
            "once",
            "--quiet",
            "--chroot",
            "/",
            "--cwd",
            workdir,
            "--rlimit_cpu",
            str(DEFAULT_CPU_SECONDS),
            "--rlimit_as",
            str(DEFAULT_MEMORY_BYTES),
            "--rlimit_nofile",
            str(DEFAULT_MAX_OPEN_FILES),
            "--rlimit_fsize",
            str(DEFAULT_MAX_FILE_BYTES),
            "--",
            *cmd,
        ]
    if backend == "seatbelt":
        profile_path = os.path.join(workdir, "seatbelt.sb")
        with open(profile_path, "w", encoding="utf-8") as handle:
            handle.write(_seatbelt_profile(workdir))
        return ["sandbox-exec", "-f", profile_path, "--", *cmd]
    return cmd


class PythonSandbox(Protocol):
    async def run_code(self, code: str) -> dict[str, Any]: ...


class RunPythonArgs(BaseModel):
    code: str = Field(..., min_length=1, max_length=MAX_CODE_CHARS)


class SubprocessPythonSandbox:
    """Exécute le code dans un fils `python -I -c`, isolé et limité."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        cpu_seconds: int = DEFAULT_CPU_SECONDS,
        memory_bytes: int = DEFAULT_MEMORY_BYTES,
        max_open_files: int = DEFAULT_MAX_OPEN_FILES,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_code_chars: int = MAX_CODE_CHARS,
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ) -> None:
        self._timeout = timeout
        self._cpu_seconds = cpu_seconds
        self._memory_bytes = memory_bytes
        self._max_open_files = max_open_files
        self._max_file_bytes = max_file_bytes
        self._max_code_chars = max_code_chars
        self._max_output_chars = max_output_chars

    def _preamble(self) -> str:
        """Tourne avant le code utilisateur, dans le process fils."""
        return (
            "import resource, socket, os, subprocess\n"
            "def _limit(res, val):\n"
            "    try:\n"
            "        resource.setrlimit(res, (val, val))\n"
            "    except (ValueError, OSError):\n"
            "        pass  # ex. RLIMIT_AS non supporté sur macOS, actif sur Linux\n"
            f"_limit(resource.RLIMIT_CPU, {self._cpu_seconds})\n"
            f"_limit(resource.RLIMIT_AS, {self._memory_bytes})\n"
            f"_limit(resource.RLIMIT_NOFILE, {self._max_open_files})\n"
            f"_limit(resource.RLIMIT_FSIZE, {self._max_file_bytes})\n"
            "def _bloque(*_a, **_k):\n"
            "    raise RuntimeError('bloqué dans la sandbox')\n"
            "socket.socket = _bloque\n"
            "socket.create_connection = _bloque\n"
            "socket.getaddrinfo = _bloque\n"
            "os.system = _bloque\n"
            "os.popen = _bloque\n"
            "subprocess.Popen = _bloque\n"
            "subprocess.run = _bloque\n"
            "subprocess.call = _bloque\n"
        )

    async def run_code(self, code: str) -> dict[str, Any]:
        if len(code) > self._max_code_chars:
            raise ToolError(
                "run_python",
                f"code trop long ({len(code)} > {self._max_code_chars} car.)",
            )
        # 13c : pre-check statique — un code dangereux n'est jamais exécuté.
        backend = detect_os_backend()
        issues = static_precheck(code)
        if issues:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "bloqué par le pre-check statique : " + "; ".join(issues),
                "truncated": False,
                "precheck": issues,
                "backend": backend,
            }
        program = self._preamble() + "\n" + code
        with tempfile.TemporaryDirectory(prefix="investia-sandbox-") as tmpdir:
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "HOME": tmpdir,
                "TMPDIR": tmpdir,
            }
            command = os_wrap_command([sys.executable, "-I", "-c", program], tmpdir)
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=tmpdir,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except TimeoutError:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await proc.wait()
                raise ToolError(
                    "run_python", f"timeout après {self._timeout:g} s (processus tué)"
                ) from None
        secrets = _secret_values()
        out = _redact(stdout.decode("utf-8", errors="replace"), secrets)
        err = _redact(stderr.decode("utf-8", errors="replace"), secrets)
        truncated = (
            len(out) > self._max_output_chars or len(err) > self._max_output_chars
        )
        return {
            "exit_code": proc.returncode,
            "stdout": out[: self._max_output_chars],
            "stderr": err[: self._max_output_chars],
            "truncated": truncated,
            "backend": backend,
        }


class RunPythonTool(BaseTool[RunPythonArgs]):
    name = "run_python"
    description = (
        "Exécute du code Python dans une sandbox isolée (sans réseau, limites "
        "CPU/RAM/timeout). Entrée : code (1-10 000 car.). Sortie : exit_code, stdout, "
        "stderr tronqués à 20 000 car., source et horodatage. Pour tous les calculs "
        "(ratios, backtests, agrégations) : ne calcule jamais de tête."
    )
    args_schema = RunPythonArgs

    def __init__(self, sandbox: PythonSandbox) -> None:
        self._sandbox = sandbox

    async def run(self, args: RunPythonArgs) -> dict[str, Any]:
        try:
            result = await self._sandbox.run_code(args.code)
        except ToolError:
            raise
        except Exception as error:
            raise ToolError(self.name, str(error)) from error
        return {
            **result,
            "source": "sandbox",
            "timestamp": datetime.now(UTC).isoformat(),
        }
