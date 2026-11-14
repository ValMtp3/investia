"""Outil get_forecast — prévision probabiliste d'un cours via Timestral (17a)."""

from typing import Any

from pydantic import Field

from investia.market.base import MarketDataError, MarketDataService
from investia.market.forecast import Forecaster, ForecastError
from investia.tools.base import BaseTool, SymbolArgs, ToolError

MIN_HISTORY_POINTS = 5

DISCLAIMER = (
    "Prévision probabiliste (Mistral Timestral) avec bande q10-q90 — "
    "ce n'est pas une certitude. Simulation, pas un conseil en investissement."
)


class ForecastArgs(SymbolArgs):
    days: int = Field(30, ge=7, le=90, description="Fenêtre d'historique en jours.")
    horizon: int = Field(5, ge=1, le=30, description="Nombre de jours prédits.")


class GetForecastTool(BaseTool[ForecastArgs]):
    name = "get_forecast"
    description = (
        "Prévision probabiliste du cours d'un actif pour les prochains jours "
        "(médiane + bande d'incertitude q10-q90), produite par le modèle de "
        "séries temporelles Timestral à partir de l'historique récent. "
        "Ce n'est PAS une certitude : une prévision, pas un conseil."
    )
    args_schema = ForecastArgs
    untrusted_output = True  # sortie API externe : scannée anti-injection (13b)

    def __init__(self, market: MarketDataService, forecaster: Forecaster) -> None:
        self._market = market
        self._forecaster = forecaster

    async def run(self, args: ForecastArgs) -> dict[str, Any]:
        symbol = args.symbol.strip().upper()
        try:
            history = await self._market.get_history(symbol, args.days)
        except MarketDataError as error:
            raise ToolError(self.name, str(error)) from error
        if len(history) < MIN_HISTORY_POINTS:
            raise ToolError(
                self.name,
                f"historique insuffisant pour {symbol} : {len(history)} points "
                f"(minimum {MIN_HISTORY_POINTS})",
            )
        timestamps = [point.timestamp.isoformat() for point in history]
        values = [float(point.value) for point in history]
        try:
            forecast = await self._forecaster.forecast(timestamps, values, args.horizon)
        except ForecastError as error:
            raise ToolError(self.name, str(error)) from error
        return {
            "symbol": symbol,
            "days_history": len(history),
            "horizon": forecast["horizon"],
            "median": forecast["median"],
            "low": forecast["low"],
            "high": forecast["high"],
            "timestamps_forecast": forecast["timestamps_forecast"],
            "model": forecast["model"],
            "disclaimer": DISCLAIMER,
        }
