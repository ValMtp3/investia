"""Tests du build_dataset (spec 22a) : JSONL de traces -> cases-live.yaml."""

import json
from pathlib import Path

import yaml

from investia.evals.build_dataset import build_dataset, normalize_question
from investia.evals.runner import load_cases


def _line(**kw) -> str:
    base = {
        "id": "run-1",
        "question": "prix AAPL ?",
        "answer": "AAPL vaut 344.63 $.",
        "model": "gpt-6-luna",
        "status": "ok",
        "turns": 2,
        "total_cost_cents": 0.02,
        "created_at": "2026-11-14T10:00:00+00:00",
        "step_kinds": ["tool_call"],
        "tools_used": ["get_quote"],
    }
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


def _write(tmp_path, lines: list[str]) -> Path:
    src = tmp_path / "traces.jsonl"
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return src


def test_normalize_question():
    assert normalize_question("  Prix   AAPL ? ") == "prix aapl ?"


def test_build_dataset_filtre_dedup_et_ecrit_yaml(tmp_path):
    """22a : status=ok + question/answer non vides, dédup par question normalisée."""
    src = _write(
        tmp_path,
        [
            _line(id="a1", question="prix AAPL ?"),
            # doublon de a1 (même question normalisée) : on garde le plus récent
            _line(
                id="a2",
                question="  Prix   AAPL ? ",
                created_at="2026-11-14T12:00:00+00:00",
            ),
            _line(id="b1", question="historique BTC ?", status="blocked"),  # filtré
            _line(id="b2", question="", answer="x"),  # filtré
            _line(id="b3", question="q sans réponse", answer=""),  # filtré
            _line(
                id="c1",
                question="analyse portefeuille",
                tools_used=["get_portfolio", "get_quote"],
            ),
        ],
    )
    out = tmp_path / "cases-live.yaml"
    info = build_dataset(src, out, limit=50, seed=42)
    assert info["count"] == 2  # a2 (le plus récent) + c1
    cases = load_cases(out)
    by_id = {c.id: c for c in cases}
    assert set(by_id) == {"trace-a2", "trace-c1"}
    assert by_id["trace-c1"].expected_tool == "get_portfolio"  # premier tools_used
    assert by_id["trace-c1"].mock_final == "AAPL vaut 344.63 $."
    # le YAML est relisable par load_cases (contrat)
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "cases" in data


def test_build_dataset_seed_deterministe(tmp_path):
    """22a : deux appels avec le même seed -> YAML byte-identique."""
    lines = [_line(id=f"r{i}", question=f"question {i} ?") for i in range(20)]
    src = _write(tmp_path, lines)
    out1 = tmp_path / "c1.yaml"
    out2 = tmp_path / "c2.yaml"
    build_dataset(src, out1, limit=8, seed=42)
    build_dataset(src, out2, limit=8, seed=42)
    assert out1.read_bytes() == out2.read_bytes()
    assert len(load_cases(out1)) == 8


def test_build_dataset_limit_tronque(tmp_path):
    lines = [_line(id=f"r{i}", question=f"question {i} ?") for i in range(10)]
    src = _write(tmp_path, lines)
    out = tmp_path / "c.yaml"
    info = build_dataset(src, out, limit=3, seed=1)
    assert info["count"] == 3
    assert len(load_cases(out)) == 3
