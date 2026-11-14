"""Configuration de l'application, chargée et validée depuis l'environnement."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 16b : même valeur que DEFAULT_LOCAL_EMBEDDING_MODEL (memory.embeddings) —
# dupliquée ici pour éviter un import circulaire config <-> memory.
DEFAULT_LOCAL_EMBEDDING_MODEL = "Qwen3-Embedding-0.6B"

# 17a : mêmes valeurs que market.forecast (import circulaire sinon).
DEFAULT_TIMESTRAL_MODEL = "timestral-1-0-209m"
DEFAULT_TIMESTRAL_BASE_URL = "https://api.mistral.ai/v1"

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

    # 15b : signature JWS des Agent Cards A2A (vide = cards non signées)
    agent_card_signing_key: SecretStr | None = None
    agent_card_signing_kid: str = "investia-2026"
    agent_card_signing_alg: str = "ES256"

    # 16b : embeddings locaux (sentence-transformers) ou OpenRouter (défaut)
    embeddings_backend: Literal["openrouter", "local"] = "openrouter"
    local_embedding_model: str = Field(
        default=DEFAULT_LOCAL_EMBEDDING_MODEL,
        pattern=r"^[A-Za-z0-9._/-]+$",
    )

    # 17a : prévision de séries temporelles via l'API Timestral (Mistral)
    timestral_model: str = Field(
        default=DEFAULT_TIMESTRAL_MODEL, pattern=r"^[A-Za-z0-9._-]+$"
    )
    timestral_base_url: str = DEFAULT_TIMESTRAL_BASE_URL

    # 16c : compaction du contexte de run_agent (0 = désactivé)
    context_max_tokens: int | None = 100_000
    compaction_keep_last_turns: int = Field(default=4, ge=1, le=20)

    # 17e : tool policy pré-schéma + double dial approval × sandbox (Codex/OpenClaw).
    # csv d'outils à ne jamais envoyer au modèle (ex. "run_python,web_search")
    disabled_tools: str = ""
    # "quoi" : order = validation humaine des ordres (D57, défaut) ; off = aucune
    approval_mode: Literal["order", "off"] = "order"
    # "où" : os = sandbox OS fail-closed (17c, défaut) ; off = opt-in dev explicite
    sandbox_mode: Literal["os", "off"] = "os"

    # 17f : plafond de coût par appel LLM, côté client (le gateway a aussi son
    # propre plafond max_budget dans deploy/litellm/config.yaml)
    llm_budget_cents_per_call: float = Field(default=100.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuration, mis en cache en mémoire."""
    return Settings()
