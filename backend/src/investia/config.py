"""Configuration de l'application, chargée et validée depuis l'environnement."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration validée au démarrage. Aucun secret n'a de valeur par défaut."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Requis dès l'étape 0
    database_url: SecretStr
    redis_url: SecretStr
    litellm_base_url: str
    litellm_master_key: SecretStr
    app_secret_key: SecretStr

    # Optionnels à l'étape 0, requis quand le code s'en sert (étape 1)
    openrouter_api_key: SecretStr | None = None
    mistral_api_key: SecretStr | None = None
    typesafe_api_key: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None
    eodhd_api_key: SecretStr | None = None
    coingecko_demo_api_key: SecretStr | None = None
    stooq_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuration, mis en cache en mémoire."""
    return Settings()
