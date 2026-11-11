"""Configuration de l'application, chargée et validée depuis l'environnement."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Le jeton admin (en-tête X-Admin-Token, D51) ne doit jamais être vide ni devinable.
MIN_ADMIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Configuration validée au démarrage. Aucun secret n'a de valeur par défaut."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Requis dès l'étape 0
    database_url: SecretStr
    redis_url: SecretStr
    litellm_base_url: str
    litellm_master_key: SecretStr
    app_secret_key: SecretStr = Field(min_length=MIN_ADMIN_SECRET_LENGTH)

    # Optionnels à l'étape 0, requis quand le code s'en sert (étape 1)
    openrouter_api_key: SecretStr | None = None
    mistral_api_key: SecretStr | None = None
    typesafe_api_key: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None
    eodhd_api_key: SecretStr | None = None
    twelvedata_api_key: SecretStr | None = None
    massive_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None
    nutrient_api_key: SecretStr | None = None
    coingecko_demo_api_key: SecretStr | None = None
    stooq_api_key: SecretStr | None = None

    # Origin autorisé pour les appels cross-origin du dashboard en dev (CORS)
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuration, mis en cache en mémoire."""
    return Settings()
