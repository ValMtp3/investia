"""Tests TDD 23h : dataset pinning (sha256 YAML dans eval_runs, changelog, verify)."""

import hashlib
import json
from pathlib import Path

import yaml


def _write_cases(tmp_path: Path, n: int = 3) -> Path:
    cases = {
        "cases": [
            {
                "id": f"c{i}",
                "question": f"question {i} ?",
                "mock_final": "ok",
                "expected_tool": "get_quote",
            }
            for i in range(n)
        ]
    }
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(cases, allow_unicode=True), encoding="utf-8")
    return path


class FakeEvalStore:
    def __init__(self):
        self.runs: list[dict] = []

    async def start_eval_run(self, model, mode, dataset_sha256=None):
        self.runs.append(
            {"model": model, "mode": mode, "dataset_sha256": dataset_sha256}
        )
        return "eval-run-1"

    async def log_result(self, run_id, case_id, metric, score):
        pass


async def test_run_evals_enregistre_le_sha256_du_dataset(tmp_path):
    from investia.evals.runner import load_cases, run_evals

    cases_path = _write_cases(tmp_path)
    expected = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    store = FakeEvalStore()
    await run_evals(
        load_cases(cases_path),
        eval_store=store,
        mode="mock",
        cases_path=cases_path,  # 23h : pinning
    )
    assert store.runs[0]["dataset_sha256"] == expected


async def test_run_evals_sans_cases_path_garde_none(tmp_path):
    """Rétrocompatible : sans cases_path, pas de hash (None)."""
    from investia.evals.runner import load_cases, run_evals

    cases_path = _write_cases(tmp_path)
    store = FakeEvalStore()
    await run_evals(load_cases(cases_path), eval_store=store, mode="mock")
    assert store.runs[0]["dataset_sha256"] is None


def test_build_dataset_ecrit_sha256_yaml_et_changelog(tmp_path):
    from investia.evals.build_dataset import build_dataset

    src = tmp_path / "traces.jsonl"
    lines = [
        json.dumps(
            {
                "id": f"run-{i}",
                "question": f"prix action {i} ?",
                "answer": f"réponse {i}",
                "model": "gpt-6-luna",
                "status": "ok",
                "turns": 2,
                "total_cost_cents": 0.02,
                "created_at": f"2026-11-14T10:0{i}:00+00:00",
                "step_kinds": ["tool_call"],
                "tools_used": ["get_quote"],
            },
            ensure_ascii=False,
        )
        for i in range(3)
    ]
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "generated" / "cases-live.yaml"
    info = build_dataset(src, out, limit=10, seed=42)

    # 23h : le YAML est pinné (sha256 à côté) + changelog
    sha_file = Path(str(out) + ".sha256")
    assert sha_file.exists()
    expected = hashlib.sha256(out.read_bytes()).hexdigest()
    assert sha_file.read_text(encoding="utf-8").strip() == expected
    assert info["sha256"] == expected
    changelog = tmp_path / "generated" / "DATASET_CHANGELOG.md"
    assert changelog.exists()
    line = changelog.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert expected in line
    assert str(info["count"]) in line


def test_verify_ok_puis_ko_apres_tampon(tmp_path, capsys):
    from investia.evals.__main__ import main

    cases_path = _write_cases(tmp_path)
    expected = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    assert main(["verify", "--cases", str(cases_path), "--sha256", expected]) == 0
    # fichier modifié -> hash différent -> exit 1
    cases_path.write_text(
        yaml.safe_dump(
            {"cases": [{"id": "x", "question": "autre ?", "mock_final": "ok"}]}
        ),
        encoding="utf-8",
    )
    assert main(["verify", "--cases", str(cases_path), "--sha256", expected]) == 1
    # sans --sha256 : compare avec le fichier .sha256 à côté s'il existe
    Path(str(cases_path) + ".sha256").write_text(expected + "\n", encoding="utf-8")
    assert main(["verify", "--cases", str(cases_path)]) == 1  # le YAML a changé


def test_migration_0015_chainee_sur_0014():
    import re
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    content = (versions / "0015_eval_runs_dataset_sha256.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r'revision = "0015_eval_runs_dataset_sha256"', content)
    assert re.search(r'down_revision = "0014_semantic_cache_namespace"', content)
    assert "dataset_sha256" in content
