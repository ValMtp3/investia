"""Outil run_python — exécution de code Python dans un sous-process isolé (étape 12g).

Menace : code généré par le LLM de l'agent (maladresse : boucle infinie, écriture
massive, fork, fuite de secrets), pas un attaquant externe. Isolation, zéro dépendance :
tempdir dédié supprimé après le run, env whitelist (aucun secret), `python -I`,
limites `resource` (CPU/RAM/fichiers) posées dans le preamble, réseau et sous-process
bloqués (best effort, patch de socket/subprocess/os.system), timeout avec kill du
groupe de processus. Sans isolation noyau (macOS) : documenté dans la spec 12g.
"""

import asyncio
import os
import re
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
        program = self._preamble() + "\n" + code
        with tempfile.TemporaryDirectory(prefix="investia-sandbox-") as tmpdir:
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "HOME": tmpdir,
                "TMPDIR": tmpdir,
            }
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                "-c",
                program,
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
