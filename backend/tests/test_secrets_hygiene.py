"""Hygiène des secrets : .env jamais commité, .env.example sans valeurs."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SECRET_SUFFIXES = ("_KEY", "_PASSWORD", "_SECRET")


def test_env_file_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", ".env"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, ".env doit être ignoré par git (.gitignore)"


def test_env_example_exists_and_has_no_secret_values():
    env_example = REPO_ROOT / ".env.example"
    assert env_example.exists(), ".env.example doit exister à la racine"
    for line in env_example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        assert separator, f"ligne invalide dans .env.example : {line!r}"
        if name.endswith(SECRET_SUFFIXES):
            assert value.strip() == "", (
                f"{name} ne doit pas avoir de valeur dans .env.example"
            )
