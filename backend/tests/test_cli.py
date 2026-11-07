"""Test de la CLI : --help fonctionne sans toucher aux settings."""

import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_cli_help():
    result = subprocess.run(
        ["uv", "run", "python", "-m", "investia.cli", "--help"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "question" in result.stdout
