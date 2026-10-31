"""Tests de config de la CI GitHub Actions — parse le YAML du workflow."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_FILE = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def load_ci() -> dict:
    return yaml.safe_load(CI_FILE.read_text(encoding="utf-8"))


def test_ci_file_exists_and_has_four_jobs():
    assert CI_FILE.exists(), ".github/workflows/ci.yml doit exister"
    jobs = load_ci()["jobs"]
    assert {"ruff", "format", "ty", "pytest"} <= set(jobs.keys())


def test_pytest_job_runs_coverage_with_threshold_80():
    steps = load_ci()["jobs"]["pytest"]["steps"]
    run_steps = [step.get("run", "") for step in steps if "run" in step]
    assert any("--cov-fail-under=80" in run_cmd for run_cmd in run_steps)


def test_pytest_job_has_postgres_pgvector_and_redis_services():
    services = load_ci()["jobs"]["pytest"]["services"]
    assert services["postgres"]["image"] == "pgvector/pgvector:pg17"
    assert services["redis"]["image"] == "redis:8"
