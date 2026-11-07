"""Tests de configuration du projet : pyproject.toml et uv.lock."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def test_pyproject_exists_and_requires_python_312():
    pyproject = BACKEND_DIR / "pyproject.toml"
    assert pyproject.exists(), "backend/pyproject.toml doit exister"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    requires_python = data["project"]["requires-python"]
    assert "3.12" in requires_python, (
        f"requires-python doit contenir 3.12, trouvé : {requires_python}"
    )


def test_uv_lock_exists():
    assert (BACKEND_DIR / "uv.lock").exists(), (
        "backend/uv.lock doit exister (lancer `uv lock`)"
    )
