"""17e : tool policy pré-schéma (OpenClaw) + double dial approval × sandbox (Codex).

Un outil refusé par la policy n'est jamais envoyé au modèle (pas de schéma) :
le filtrage se fait avant la construction des tool_specs dans la boucle.

`tool_policy_from_settings` compose la policy depuis la config :
- `DISABLED_TOOLS` (csv) ;
- si `SANDBOX_MODE=os` et fail-closed actif (17c) et qu'aucun backend
  d'isolation OS n'est disponible → `run_python` est retiré pré-schéma
  (le fail-closed runtime de 17c reste en dernier recours).
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from investia.tools.python_sandbox import (
    BACKEND_BINARIES,
    SandboxUnavailableError,
    check_backend_available,
    detect_os_backend,
    fail_closed_enabled,
)

if TYPE_CHECKING:
    from investia.config import Settings


def any_sandbox_backend_available() -> bool:
    """True si au moins un backend d'isolation est disponible.

    23i : le sidecar Go compte (socket unix présent), comme nsjail/sandbox-exec.
    """
    try:
        if detect_os_backend() == "sidecar":
            check_backend_available("sidecar")
            return True
    except (SandboxUnavailableError, ValueError):
        pass
    for backend in BACKEND_BINARIES:
        try:
            check_backend_available(backend)
        except SandboxUnavailableError:
            continue
        return True
    return False


def tool_policy_from_settings(
    settings: "Settings", *, sandbox_available: bool | None = None
) -> Callable[[str], bool] | None:
    """Policy composée : `name -> False` pour les outils à ne pas envoyer au modèle.

    Retourne None si aucun outil n'est désactivé (comportement historique).
    `sandbox_available` injectable pour les tests ; None = détection auto.
    """
    disabled = {t.strip() for t in settings.disabled_tools.split(",") if t.strip()}
    if settings.sandbox_mode == "os" and fail_closed_enabled():
        if sandbox_available is None:
            sandbox_available = any_sandbox_backend_available()
        if not sandbox_available:
            disabled.add("run_python")
    if not disabled:
        return None
    return lambda name: name not in disabled
