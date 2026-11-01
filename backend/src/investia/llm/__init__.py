"""Package llm : client LiteLLM + routeur + config modèles."""

from investia.config import Settings
from investia.llm.client import LlmClient, LlmResponse
from investia.llm.decisions import DecisionAnswer, DecisionClient
from investia.llm.errors import LlmError
from investia.llm.models import ModelsConfig, load_models_config
from investia.llm.router import choose

__all__ = [
    "DecisionAnswer",
    "DecisionClient",
    "LlmClient",
    "LlmError",
    "LlmResponse",
    "ModelsConfig",
    "build_decision_client",
    "build_llm_client",
    "choose",
    "load_models_config",
]

DEFAULT_BUDGET_CENTS = 100.0


def build_llm_client(
    settings: Settings, budget_cents: float = DEFAULT_BUDGET_CENTS
) -> LlmClient:
    return LlmClient(
        base_url=settings.litellm_base_url,
        master_key=settings.litellm_master_key,
        models=load_models_config(),
        budget_cents=budget_cents,
    )


def build_decision_client(settings: Settings) -> DecisionClient:
    return DecisionClient(
        base_url=settings.litellm_base_url,
        master_key=settings.litellm_master_key,
    )
