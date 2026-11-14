"""Redaction PII/secrets avant stockage (spec 13a).

Pourquoi : les payloads de traces contiennent les sorties brutes des outils
(web, PDF, erreurs) — un contenu externe peut embarquer une clé API, un e-mail,
un téléphone. Ce module masque tout ça avant l'INSERT en base.

Deux couches :
- `RegexRedactor` : toujours actif, 100 % stdlib (valeurs des secrets de l'env
  + patterns usuels). Déterministe, aucun réseau.
- `PresidioRedactor` : renfort PII via Presidio **si** importable et si un
  modèle spaCy est présent localement. Sinon repli sur le regex, sans crash
  ni téléchargement (aucun appel réseau au runtime).
"""

import os
import re
from functools import lru_cache
from typing import Any, Protocol

REDACTED = "***REDACTE***"
MIN_SECRET_LEN = 8
SECRET_NAME_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)

# Patterns usuels de secrets et de PII (clés API, tokens, e-mails, téléphones FR).
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"0[1-9](?:[ .-]?\d{2}){4}"),
]


class Redactor(Protocol):
    def redact(self, text: str) -> str: ...


def env_secret_values(environ: dict[str, str] | None = None) -> list[str]:
    """Valeurs des variables d'env ressemblant à des secrets (triées par taille)."""
    env = os.environ if environ is None else environ
    values = {
        value
        for name, value in env.items()
        if SECRET_NAME_RE.search(name) and len(value) >= MIN_SECRET_LEN
    }
    return sorted(values, key=len, reverse=True)


class RegexRedactor:
    """Masque les secrets connus de l'env et les patterns usuels. Zéro dépendance."""

    def __init__(self, secrets: list[str] | None = None) -> None:
        self._secrets = secrets if secrets is not None else env_secret_values()

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        for pattern in SECRET_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text


@lru_cache(maxsize=1)
def _presidio_engines() -> tuple[Any, Any] | None:
    """Moteurs Presidio si importables AVEC un modèle spaCy local, sinon None.

    Mis en cache : le chargement de spaCy coûte plusieurs secondes et lève
    OSError quand aucun modèle n'est installé — on ne le tente qu'une fois.
    Aucun téléchargement réseau au runtime.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        return AnalyzerEngine(), AnonymizerEngine()
    except Exception:
        return None


class PresidioRedactor:
    """Renfort PII via Presidio, avec repli regex si absent ou sans modèle local."""

    def __init__(self, fallback: Redactor | None = None) -> None:
        self._fallback = fallback or RegexRedactor()
        engines = _presidio_engines()
        if engines is None:
            self._analyzer = None
            self._anonymizer = None
        else:
            self._analyzer, self._anonymizer = engines

    @property
    def active(self) -> bool:
        return self._analyzer is not None

    def redact(self, text: str) -> str:
        if self._analyzer is None or self._anonymizer is None:
            return self._fallback.redact(text)
        try:
            results = self._analyzer.analyze(text=text, language="fr")
            if not results:
                return text
            return self._anonymizer.anonymize(text=text, analyzer_results=results).text
        except Exception:
            return self._fallback.redact(text)


class ChainRedactor:
    """Applique chaque redactor à la suite (idempotent)."""

    def __init__(self, redactors: list[Redactor]) -> None:
        self._redactors = redactors

    def redact(self, text: str) -> str:
        for redactor in self._redactors:
            text = redactor.redact(text)
        return text


def default_redactor() -> Redactor:
    """Redactor par défaut : regex (env + patterns) puis Presidio si disponible."""
    regex = RegexRedactor()
    return ChainRedactor([regex, PresidioRedactor(regex)])


def redact_value(value: Any, redactor: Redactor) -> Any:
    """Parcourt récursivement les dict/list et redacte chaque chaîne."""
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, dict):
        return {key: redact_value(item, redactor) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item, redactor) for item in value]
    return value
