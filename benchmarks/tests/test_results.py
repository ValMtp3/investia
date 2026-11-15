"""Tests 23h : schéma de results.json + vérification du pin du dataset."""

import hashlib
import json
import sys
from pathlib import Path

import yaml

BENCH_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BENCH_DIR.parent
DEFAULT_CASES = REPO_ROOT / "evals" / "cases.yaml"
sys.path.insert(0, str(BENCH_DIR))

from run_benchmark import (  # noqa: E402
    GATE_METRICS,
    build_report,
    main,
    sha256_file,
    verify_dataset,
)

REQUIRED_KEYS = {
    "agent",
    "commit",
    "dataset_sha256",
    "n_cases",
    "pass1",
    "metrics",
    "cost_cents_total",
    "duration_ms",
    "generated_at",
}


def _mini_cases(tmp_path: Path) -> Path:
    cases = {
        "cases": [
            {
                "id": "t1",
                "question": "Quelle est la tendance du CAC40 ?",
                "expected_tool": "get_index",
                "mock_tool_call": {
                    "name": "get_quote",
                    "arguments": {"symbol": "AAPL"},
                },
                "mock_final": "Le CAC40 monte.",
            }
        ]
    }
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(cases, allow_unicode=True), encoding="utf-8")
    return path


def test_verify_dataset_ok_and_mismatch(tmp_path: Path):
    cases = _mini_cases(tmp_path)
    actual = sha256_file(cases)
    assert verify_dataset(cases, actual) == actual  # pin explicite OK
    Path(str(cases) + ".sha256").write_text(actual + "\n", encoding="utf-8")
    assert verify_dataset(cases) == actual  # sidecar OK
    try:
        verify_dataset(cases, "0" * 64)
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("un pin qui ne matche pas doit lever SystemExit(1)")


def test_build_report_schema_and_pass1():
    summary = {
        "run_id": None,
        "mode": "mock",
        "results": [
            {"case_id": "a", "status": "ok", "metrics": {m: 1.0 for m in GATE_METRICS}},
            {
                "case_id": "b",
                "status": "ok",
                "metrics": {**{m: 1.0 for m in GATE_METRICS}, "tool_used": 0.0},
            },
        ],
    }
    report = build_report(summary, "abc123", "deadbeef", 12.5)
    assert REQUIRED_KEYS <= set(report)
    assert report["n_cases"] == 2
    assert report["pass1"] == 0.5
    assert report["metrics"]["tool_used"] == 0.5
    assert report["dataset_sha256"] == "abc123"
    assert report["cost_cents_total"] == 0.0


def test_main_produces_results_json_with_dataset_pin(tmp_path: Path):
    cases = _mini_cases(tmp_path)
    out = tmp_path / "results.json"
    rc = main(["--cases", str(cases), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert REQUIRED_KEYS <= set(report)
    assert report["dataset_sha256"] == hashlib.sha256(cases.read_bytes()).hexdigest()
    assert report["n_cases"] == 1
    assert 0.0 <= report["pass1"] <= 1.0
    assert report["agent"] == "investia-harness"


def test_main_refuses_tampered_dataset(tmp_path: Path):
    cases = _mini_cases(tmp_path)
    out = tmp_path / "results.json"
    main(["--cases", str(cases), "--out", str(out)])
    cases.write_text("cases: []\n", encoding="utf-8")  # dataset modifié après pin
    Path(str(cases) + ".sha256").write_text("0" * 64 + "\n", encoding="utf-8")
    try:
        main(["--cases", str(cases), "--out", str(out)])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("un dataset modifié doit être refusé (exit 1)")


def test_default_dataset_pin_matches_harbor_yaml():
    """Le sha256 pinné dans harbor/harbor.yaml doit matcher evals/cases.yaml."""
    harbor_yaml = (BENCH_DIR / "harbor" / "harbor.yaml").read_text(encoding="utf-8")
    pinned = None
    for line in harbor_yaml.splitlines():
        if "sha256:" in line and "dataset" not in line:
            pinned = line.split("sha256:")[1].strip().strip('"')
    assert pinned is not None, "sha256 du dataset absent de harbor.yaml"
    assert sha256_file(DEFAULT_CASES) == pinned


def test_results_json_committed_is_fresh_schema():
    results = BENCH_DIR / "results.json"
    if not results.exists():
        return  # généré par `uv run python run_benchmark.py`, pas en CI
    report = json.loads(results.read_text(encoding="utf-8"))
    assert REQUIRED_KEYS <= set(report)
    assert report["dataset_sha256"] == sha256_file(DEFAULT_CASES)
