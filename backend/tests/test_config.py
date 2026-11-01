"""Tests de la configuration (Pydantic Settings) et du démarrage de l'app."""

import pytest
from pydantic import ValidationError

from investia.config import Settings
from investia.main import create_app

REQUIRED_VARS = (
    "DATABASE_URL",
    "REDIS_URL",
    "LITELLM_BASE_URL",
    "LITELLM_MASTER_KEY",
    "APP_SECRET_KEY",
)

OPTIONAL_API_KEYS = (
    "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY",
    "TYPESAFE_API_KEY",
    "FINNHUB_API_KEY",
    "EODHD_API_KEY",
    "COINGECKO_DEMO_API_KEY",
    "STOOQ_API_KEY",
)


def test_settings_missing_env_lists_required_fields(monkeypatch):
    for var in (*REQUIRED_VARS, *OPTIONAL_API_KEYS):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    missing = {str(error["loc"][0]).upper() for error in exc_info.value.errors()}
    assert set(REQUIRED_VARS) <= missing


def test_settings_optional_api_keys_default_to_none(monkeypatch):
    values = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "LITELLM_BASE_URL": "http://localhost:4000",
        "LITELLM_MASTER_KEY": "sk-test",
        "APP_SECRET_KEY": "test-secret",
    }
    for var, value in values.items():
        monkeypatch.setenv(var, value)
    for var in OPTIONAL_API_KEYS:
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    for var in OPTIONAL_API_KEYS:
        assert getattr(settings, var.lower()) is None


def test_create_app_without_config_exits_1_with_clear_message(monkeypatch, capsys):
    for var in (*REQUIRED_VARS, *OPTIONAL_API_KEYS):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit) as exc_info:
        create_app()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err
    for var in REQUIRED_VARS:
        assert var in output, f"le message d'erreur doit nommer {var}"
    assert "Traceback" not in output, "pas de stack trace dans le message"
