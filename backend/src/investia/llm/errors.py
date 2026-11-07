"""Erreurs du client LLM."""


class LlmError(Exception):
    """Erreur d'appel au gateway — message clair, jamais de réponse fabriquée."""
