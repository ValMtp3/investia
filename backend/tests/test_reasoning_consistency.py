"""Tests TDD de la brique 12c : self-consistency (vote + k runs parallèles + evals)."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from investia.agent.reasoning import extract_confidence, normalize_answer, vote


# --- Task 1 : fonctions pures de vote ---


def test_normalize_answer_casse_et_espaces():
    assert normalize_answer("  Réponse\n A  ") == "réponse a"


def test_extract_confidence_present():
    assert extract_confidence("## Confiance\n80\n") == 80
    assert extract_confidence("## confiance : 65") == 65


def test_extract_confidence_absent():
    assert extract_confidence("pas de section") == 0


def test_vote_majoritaire_gagne():
    index, consensus = vote(["Réponse A", "réponse a ", "Réponse B"])
    assert index == 0
    assert consensus == pytest.approx(2 / 3)


def test_vote_ex_aequo_confiance_la_plus_haute_gagne():
    a = "## Thèse\nA\n\n## Confiance\n50"
    b = "## Thèse\nB\n\n## Confiance\n90"
    c = "## Thèse\nC\n\n## Confiance\n70"
    index, consensus = vote([a, b, c])
    assert index == 1
    assert consensus == pytest.approx(1 / 3)


def test_vote_ex_aequo_sans_confiance_premier_gagne():
    index, consensus = vote(["A", "B", "C"])
    assert index == 0
    assert consensus == pytest.approx(1 / 3)


def test_vote_un_seul_et_vide():
    assert vote(["x"]) == (0, 1.0)
    assert vote([]) == (0, 1.0)  # garde-fou, jamais appelé en pratique
