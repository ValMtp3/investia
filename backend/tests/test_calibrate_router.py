"""Tests TDD du CLI de calibration offline du routeur (chantier 23d)."""

import json
from pathlib import Path

import pytest

CASES_YAML = """
cases:
  - id: c1
    question: "résume ce texte"
    expected_model: small
    mock_final: "ok"
  - id: c2
    question: "analyse approfondie de la stratégie long terme"
    expected_model: large
    mock_final: "ok"
  - id: c3
    question: "liste les dividendes"
    expected_model: small
    mock_final: "ok"
  - id: c4
    question: "compare les scénarios macro"
    expected_model: large
    mock_final: "ok"
"""


def write_cases(tmp_path: Path) -> Path:
    path = tmp_path / "cases-live.yaml"
    path.write_text(CASES_YAML, encoding="utf-8")
    return path


def test_calibration_cases_mode_deterministe(tmp_path):
    from investia.evals.calibrate_router import calibrate_from_cases

    cases_path = write_cases(tmp_path)
    out1 = tmp_path / "cal1.json"
    out2 = tmp_path / "cal2.json"
    r1 = calibrate_from_cases(cases_path, out1, seed=42)
    r2 = calibrate_from_cases(cases_path, out2, seed=42)
    assert r1 == r2  # même seed -> même résultat
    assert json.loads(out1.read_text(encoding="utf-8")) == r1


def test_calibration_schema_et_best_dans_la_grille(tmp_path):
    from investia.evals.calibrate_router import (
        GRID_ALPHA,
        GRID_COST_WEIGHT,
        GRID_EPSILON,
        calibrate_from_cases,
    )

    result = calibrate_from_cases(
        write_cases(tmp_path), tmp_path / "c.json", seed=42, min_success=0.5
    )
    assert result["seed"] == 42
    assert isinstance(result["results"], list) and len(result["results"]) == (
        len(GRID_ALPHA) * len(GRID_EPSILON) * len(GRID_COST_WEIGHT)
    )
    best = result["best"]
    assert best["alpha"] in GRID_ALPHA
    assert best["epsilon"] in GRID_EPSILON
    assert best["cost_weight"] in GRID_COST_WEIGHT
    for key in ("mean_reward", "success_rate", "mean_cost_cents", "n"):
        assert key in best
    # la sélection respecte la contrainte de succès (0.5 atteignable : 2 cas sur 4)
    assert best["success_rate"] >= 0.5
    # chaque résultat de la grille a les métriques
    for row in result["results"]:
        assert {
            "alpha",
            "epsilon",
            "cost_weight",
            "mean_reward",
            "success_rate",
        } <= set(row)


def test_calibration_feedbacks_mode_avec_fake_store(tmp_path):
    from investia.evals.calibrate_router import calibrate_from_feedbacks

    class FakeStore:
        async def all_feedbacks(self):
            return [
                {
                    "question": "résume",
                    "model": "small",
                    "success": True,
                    "cost_cents": 1.0,
                },
                {
                    "question": "liste",
                    "model": "small",
                    "success": True,
                    "cost_cents": 1.0,
                },
                {
                    "question": "analyse stratégie",
                    "model": "large",
                    "success": True,
                    "cost_cents": 20.0,
                },
                {
                    "question": "scénario",
                    "model": "large",
                    "success": False,
                    "cost_cents": 25.0,
                },
                {
                    "question": "résume encore",
                    "model": "small",
                    "success": True,
                    "cost_cents": 1.0,
                },
                {
                    "question": "compare",
                    "model": "large",
                    "success": True,
                    "cost_cents": 18.0,
                },
            ]

    out = tmp_path / "cal.json"
    result = calibrate_from_feedbacks(FakeStore(), out, seed=7)
    assert result["seed"] == 7
    assert result["best"]["alpha"] is not None
    assert result["best"]["n"] > 0  # des feedbacks ont été rejoués
    assert json.loads(out.read_text(encoding="utf-8"))["best"] == result["best"]


def test_cli_parser_accepte_source_et_limit(tmp_path):
    from investia.evals.calibrate_router import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["--source", "cases", "--cases", str(write_cases(tmp_path)), "--seed", "1"]
    )
    assert args.source == "cases"
    assert args.seed == 1
    args2 = parser.parse_args(["--source", "feedbacks", "--min-success", "0.9"])
    assert args2.min_success == 0.9
    with pytest.raises(SystemExit):
        parser.parse_args(["--source", "inconnu"])
