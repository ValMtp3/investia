"""Routeur petit/gros modèle — règles en dur au début (Jev arrive à l'étape 1.5)."""

SMALL_KEYWORDS = (
    "résume",
    "resume",
    "liste",
    "extrais",
    "traduis",
    "explique simplement",
)
LARGE_KEYWORDS = (
    "analyse",
    "profond",
    "stratégie",
    "recommande",
    "compare",
    "scénario",
)


def choose(question: str) -> str:
    """Renvoie "small" ou "large" selon la question."""
    q = question.lower()
    if any(k in q for k in LARGE_KEYWORDS):
        return "large"
    if any(k in q for k in SMALL_KEYWORDS):
        return "small"
    return "small" if len(q) < 120 else "large"
