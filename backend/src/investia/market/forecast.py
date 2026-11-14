"""Prévision de séries temporelles via l'API Timestral de Mistral (17a).

Timestral 1.0 = modèle de fondation de forecasting zero-shot (15/10/2026) :
POST {base_url}/forecast avec {"model", "timestamps", "values", "horizon",
"quantiles"} -> prévisions probabilistes (quantiles). Client testable avec un
MockTransport httpx (zéro réseau en test). Aucun secret en dur : la clé vient
de la config (MISTRAL_API_KEY réutilisée).
"""

from typing import Any, Protocol

import httpx
from pydantic import SecretStr

DEFAULT_TIMESTRAL_BASE_URL = "https://api.mistral.ai/v1"
DEFAULT_TIMESTRAL_MODEL = "timestral-1-0-209m"
# Quantiles demandés : bande basse / médiane / bande haute.
DEFAULT_QUANTILES = [0.1, 0.5, 0.9]


class ForecastError(Exception):
    pass


class Forecaster(Protocol):
    async def forecast(
        self, timestamps: list[str], values: list[float], horizon: int
    ) -> dict[str, Any]: ...


class MistralTimestralForecaster:
    def __init__(
        self,
        api_key: SecretStr,
        base_url: str = DEFAULT_TIMESTRAL_BASE_URL,
        model: str = DEFAULT_TIMESTRAL_MODEL,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/forecast"
        self._api_key = api_key
        self._model = model
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def forecast(
        self, timestamps: list[str], values: list[float], horizon: int
    ) -> dict[str, Any]:
        if len(timestamps) != len(values) or not values:
            raise ForecastError(
                "timestamps et values doivent être de même taille non nulle"
            )
        response = await self._client.post(
            self._url,
            json={
                "model": self._model,
                "timestamps": timestamps,
                "values": values,
                "horizon": horizon,
                "quantiles": DEFAULT_QUANTILES,
            },
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
        )
        if response.status_code != 200:
            raise ForecastError(f"HTTP {response.status_code} sur /forecast")
        return self._parse(response.json(), horizon)

    def _parse(self, payload: dict[str, Any], horizon: int) -> dict[str, Any]:
        """Parse tolérant de la réponse : quantiles sous `forecast.quantiles`
        (clés "0.1"/"0.5"/"0.9") ou variantes (`predictions`, `quantile_levels`).
        Schéma exact à confirmer sur l'API live ; on reste défensif."""
        block = payload.get("forecast") or payload.get("predictions") or payload
        quantiles = block.get("quantiles") if isinstance(block, dict) else None
        if not isinstance(quantiles, dict):
            raise ForecastError("réponse /forecast sans bloc quantiles reconnaissable")
        try:
            low = [round(float(v), 2) for v in quantiles["0.1"]]
            median = [round(float(v), 2) for v in quantiles["0.5"]]
            high = [round(float(v), 2) for v in quantiles["0.9"]]
        except (KeyError, TypeError, ValueError) as error:
            raise ForecastError(
                f"quantiles illisibles dans la réponse /forecast: {error}"
            ) from error
        if not (len(low) == len(median) == len(high) == horizon):
            raise ForecastError(
                f"horizon incohérent: attendu {horizon}, reçu {len(median)} points"
            )
        timestamps_forecast = block.get("timestamps") or []
        return {
            "model": payload.get("model", self._model),
            "horizon": horizon,
            "median": median,
            "low": low,
            "high": high,
            "timestamps_forecast": list(timestamps_forecast),
        }
