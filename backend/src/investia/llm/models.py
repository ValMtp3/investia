"""Chargement de la config des modèles (noms + prix) depuis models.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    name: str
    price_input_per_m: float
    price_output_per_m: float


@dataclass(frozen=True)
class ModelsConfig:
    small: ModelConfig
    large: ModelConfig

    def by_key(self, key: str) -> ModelConfig:
        return {"small": self.small, "large": self.large}[key]


DEFAULT_PATH = Path(__file__).parent / "models.toml"


def load_models_config(path: Path | None = None) -> ModelsConfig:
    data = tomllib.loads((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    prices = data["prices_per_million_tokens"]

    def build(key: str) -> ModelConfig:
        name = data["models"][key]
        price = prices[name]
        return ModelConfig(
            name=name,
            price_input_per_m=float(price["input"]),
            price_output_per_m=float(price["output"]),
        )

    return ModelsConfig(small=build("small"), large=build("large"))
