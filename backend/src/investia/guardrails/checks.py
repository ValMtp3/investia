"""Garde-fous en code — un prompt se contourne, une vérification Python non.

Chaque check est une fonction pure : (réponse, sorties d'outils) -> CheckResult.
"""

import re
from dataclasses import dataclass

REQUIRED_SECTIONS = ("thèse", "risques", "confiance", "sources")
FORBIDDEN_PHRASES = (
    "gain garanti",
    "gain assuré",
    "sans risque",
    "aucun risque",
    "100% sûr",
)
DISCLAIMER = "simulation — pas un conseil"

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%?")
CONFIDENCE_SECTION_RE = re.compile(r"(?is)##?\s*confiance.*?(?=##|\Z)")
ISO_DATETIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    detail: str = ""


def _numbers(text: str) -> list[float]:
    text = ISO_DATETIME_RE.sub(
        " ", text
    )  # les dates/heures ne sont pas des chiffres de marché
    values = []
    for match in NUMBER_RE.findall(text):
        cleaned = match.replace(" ", "").replace("%", "").replace(",", ".")
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def check_format(answer: str) -> CheckResult:
    """La réponse doit contenir les 4 sections : thèse, risques, confiance, sources."""
    lower = answer.lower()
    missing = [section for section in REQUIRED_SECTIONS if section not in lower]
    if missing:
        return CheckResult(False, f"sections manquantes : {', '.join(missing)}")
    return CheckResult(True)


def check_numbers(answer: str, tool_outputs: list[str]) -> CheckResult:
    """Chaque nombre de la réponse doit exister dans une sortie d'outil (±0,5 %).

    La section Confiance est exclue : appréciation du modèle, pas un chiffre de marché.
    """
    answer_without_confidence = CONFIDENCE_SECTION_RE.sub("", answer)
    output_numbers = [n for output in tool_outputs for n in _numbers(output)]
    invented = [
        value
        for value in _numbers(answer_without_confidence)
        if not any(abs(value - o) <= max(abs(o) * 0.005, 1e-9) for o in output_numbers)
    ]
    if invented:
        return CheckResult(False, f"chiffres sans source d'outil : {invented}")
    return CheckResult(True)


def check_language(answer: str) -> CheckResult:
    """Aucun langage de « conseil garanti »."""
    lower = answer.lower()
    found = [phrase for phrase in FORBIDDEN_PHRASES if phrase in lower]
    if found:
        return CheckResult(False, f"langage interdit : {', '.join(found)}")
    return CheckResult(True)


def check_disclaimer(answer: str) -> CheckResult:
    """La mention « Simulation — pas un conseil » doit être présente."""
    if DISCLAIMER in answer.lower():
        return CheckResult(True)
    return CheckResult(False, "mention « Simulation — pas un conseil » manquante")


def run_all_checks(
    answer: str, tool_outputs: list[str]
) -> list[tuple[str, CheckResult]]:
    return [
        ("format", check_format(answer)),
        ("numbers", check_numbers(answer, tool_outputs)),
        ("language", check_language(answer)),
        ("disclaimer", check_disclaimer(answer)),
    ]
