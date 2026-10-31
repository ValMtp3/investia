"""Setup commun aux tests.

Les variables d'environnement bidon sont posées AVANT l'import des modules de
test : `investia.main` crée l'app au niveau module, il ne faut pas que cet import
lève SystemExit pendant la collection. Les vrais tests posent leurs propres valeurs
avec `monkeypatch` et le cache de `get_settings` est vidé entre chaque test.
"""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LITELLM_BASE_URL", "http://localhost:4000")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from investia.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
