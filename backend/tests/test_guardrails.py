"""Tests des garde-fous en code (checks purs, zéro réseau)."""

from investia.guardrails import (
    check_disclaimer,
    check_format,
    check_language,
    check_numbers,
)

GOOD_ANSWER = """## Thèse
AAPL à 344.63 $ est en hausse de 1.2 %.

## Risques
Volatilité élevée.

## Confiance
80

## Sources
- finnhub, 2026-10-31T15:00:00Z

Simulation — pas un conseil en investissement.
"""

TOOL_OUTPUTS = [
    '{"value": 344.63, "currency": "USD", "source": "finnhub"}',
    '{"change_pct": 1.2}',
]


def test_check_format_ok_on_structured_answer():
    result = check_format(GOOD_ANSWER)
    assert result.ok, result.detail


def test_check_format_ko_when_section_missing():
    result = check_format("AAPL monte, c'est sûr. Simulation — pas un conseil.")
    assert not result.ok
    assert "risques" in result.detail.lower() or "confiance" in result.detail.lower()


def test_check_numbers_ok_when_all_numbers_come_from_tools():
    result = check_numbers(GOOD_ANSWER, TOOL_OUTPUTS)
    assert result.ok, result.detail


def test_check_numbers_ko_on_invented_number():
    answer = GOOD_ANSWER.replace("344.63", "999999")
    result = check_numbers(answer, TOOL_OUTPUTS)
    assert not result.ok
    assert "999999" in result.detail


def test_check_numbers_tolerates_rounding():
    answer = GOOD_ANSWER.replace("344.63", "344.70")  # +0.02 %
    result = check_numbers(answer, TOOL_OUTPUTS)
    assert result.ok, result.detail


def test_check_numbers_ignore_date_iso_sans_heure():
    # Une date seule (2026-10-31) dans les sources n'est pas un chiffre de marché.
    answer = GOOD_ANSWER.replace("2026-10-31T15:00:00Z", "2026-10-31")
    result = check_numbers(answer, TOOL_OUTPUTS)
    assert result.ok, result.detail


def test_check_language_ko_on_forbidden_words():
    answer = GOOD_ANSWER + "\nGain garanti !"
    result = check_language(answer)
    assert not result.ok
    assert "gain garanti" in result.detail.lower()


def test_check_language_ok_on_clean_answer():
    assert check_language(GOOD_ANSWER).ok


def test_check_disclaimer_required():
    assert check_disclaimer(GOOD_ANSWER).ok
    answer = GOOD_ANSWER.replace("Simulation — pas un conseil en investissement.", "")
    result = check_disclaimer(answer)
    assert not result.ok
