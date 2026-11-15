"""23b : canary tokens — détection d'exfiltration via le contenu externe.

Un marqueur aléatoire par run (`CANARY-<32 hex>`) est injecté dans le délimiteur
de contenu externe (voir `wrap_untrusted`). S'il réapparaît dans les arguments
d'un tool_call ou dans la réponse finale, le modèle a recopié du contenu externe
là où il ne faut pas → blocage + trace (event/step `canary_hit`).
"""

import secrets

CANARY_PREFIX = "CANARY-"
CANARY_REDACTED = "[CANARY redacted]"
CANARY_BLOCKED_MESSAGE = (
    "[TOOL_CALL BLOQUÉ : le canary du run y figurait — "
    "exfiltration de contenu externe suspectée, appel non exécuté]"
)


def generate_canary() -> str:
    """Nouveau canary aléatoire (un par run)."""
    return CANARY_PREFIX + secrets.token_hex(16)


class CanaryDetector:
    """Détecte le canary d'un run dans un texte (tool_call args, réponse finale)."""

    def __init__(self, token: str) -> None:
        self._token = token

    @property
    def token(self) -> str:
        return self._token

    def scan(self, text: str) -> bool:
        return self._token in text

    def redact(self, text: str) -> str:
        return text.replace(self._token, CANARY_REDACTED)
