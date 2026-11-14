# Spec — 17a : outil agent `get_forecast` avec le modèle Timestral (Mistral)

*Écrite le : 14/11/2026 | Étape roadmap : 17 (post-veille approfondie) | Statut : terminée le 14/11/2026 (565 tests non-integration passed / 1 skip, ruff/ty/format propres)*

## Objectif

Ajouter un outil `get_forecast(symbol, horizon)` à l'agent : à partir de l'historique de clôture (`get_history`), appeler l'API **Timestral** de Mistral (modèle de fondation de prévision de séries temporelles, publié le 15/10/2026) et renvoyer une **prévision probabiliste** (médiane + bande q10–q90) pour les prochains jours.

## Pourquoi

Veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §0) : Timestral 1.0 (5M/28M/123M/209M) est le premier modèle de prévision zero-shot de Mistral, n°1 de GIFT-Eval/TIME/fev-bench parmi les zero-shot, API preview sur La Plateforme (`timestral-1-0-209m`), inférence CPU possible en local. C'est la brique « prévision » native d'un harness financier simulé — l'agent peut confronter son analyse à une trajectoire prédite avec bande d'incertitude. Licence poids ouverts = MIT modifié (plafond 20 M$/mois de revenus — OK ici). **Ce n'est pas un conseil financier** : la simulation reste le cadre, et l'outil doit le dire.

## Contraintes

- Zéro régression : `build_tools(market, ...)` sans `forecaster` = outils identiques à aujourd'hui. Aucune dépendance nouvelle (httpx déjà là).
- Clé API : on **réutilise `MISTRAL_API_KEY`** (déjà dans la config) ; sans clé, l'outil n'est pas câblé (comme les autres connecteurs marché).
- Sécurité : la sortie vient d'une API externe → outil marqué `untrusted_output = True` (13b, scan anti-injection). En entrée on n'envoie que des timestamps + valeurs numériques de cours (jamais de PII — la redaction 13a s'applique de toute façon en amont). Pas de secret dans le code.
- Gestion d'erreurs obligatoire : HTTP ≠ 200, JSON illisible, historique insuffisant (< 5 points), horizon hors bornes → `ToolError`/`ForecastError` avec message clair.
- Le tool doit dire dans sa description que c'est une **prévision probabiliste, pas une certitude** ; le system prompt gagne une ligne là-dessus.
- Tests sans réseau (MockTransport httpx, pattern existant dans `test_memory.py`).

## Changements prévus

### `backend/src/investia/market/forecast.py` (nouveau)
- `ForecastError(Exception)`.
- `Forecaster` Protocol : `async def forecast(timestamps: list[str], values: list[float], horizon: int) -> dict`.
- `MistralTimestralForecaster(base_url="https://api.mistral.ai/v1", api_key, model="timestral-1-0-209m", http_client=None, timeout=30.0)` : `POST {base_url}/forecast` avec `{"model": model, "timestamps": [...ISO...], "values": [...], "horizon": n, "quantiles": [0.1, 0.5, 0.9]}` et header `Authorization: Bearer`. Parse la réponse (médiane + quantiles) de façon tolérante (`forecast`/`predictions`/`quantiles`…), arrondit à 2 décimales, retourne `{"model", "horizon", "median": [...], "low": [...], "high": [...], "timestamps_forecast": [...]}`. ⚠️ Le schéma exact de la réponse API sera vérifié sur l'API live (clé VPS) à l'implémentation ; le parseur reste défensif.

### `backend/src/investia/tools/forecast.py` (nouveau)
- `GetForecastArgs{symbol: str (1..20), days: int = 30 (7..90), horizon: int = 5 (1..30)}`.
- `GetForecastTool(market, forecaster)` : name `get_forecast`, `untrusted_output = True`. `run()` : historique via `market.get_history(symbol, days)` ; < 5 points → ToolError ; timestamps ISO depuis `MarketData.timestamp`, valeurs depuis `.value` ; retour + `"disclaimer": "Prévision probabiliste (Timestral) — simulation, pas un conseil en investissement."`.

### Câblage
- `tools/__init__.py` : `build_tools(..., forecaster=None)` ajoute `tools["get_forecast"] = GetForecastTool(market, forecaster)` si fourni.
- `config.py` : `timestral_model: str = "timestral-1-0-209m"` (pattern `^[A-Za-z0-9._-]+$`), `timestral_base_url: str = "https://api.mistral.ai/v1"`.
- `main.py` / `cli.py` : si `settings.mistral_api_key` présent → `MistralTimestralForecaster(...)` construit et passé à `build_tools`.
- `agent/prompts.py` : une ligne dans SYSTEM_PROMPT (« get_forecast fournit une prévision probabiliste avec bande d'incertitude — ce n'est pas une certitude »).
- `.env.example` : lignes commentées `TIMESTRAL_MODEL` / `TIMESTRAL_BASE_URL`.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest tests/test_forecast.py -q` passe (TDD) : requête HTTP (méthode, URL, header auth, body avec model/timestamps/valeurs/horizon/quantiles) ; parsing médiane + q10/q90 ; HTTP 500 → ForecastError ; JSON inattendu → ForecastError ; outil : historique < 5 points → ToolError, résultat contient median/low/high + disclaimer, contrat `to_openai_tool()` ; `build_tools` avec/sans forecaster.
- [ ] `uv run pytest -q -m "not integration"` passe en entier ; ruff/ty/format propres sur les fichiers touchés.
- [ ] Aucun appel réseau pendant les tests.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/market/forecast.py` | nouveau : `MistralTimestralForecaster`, `ForecastError`, `Forecaster` |
| `backend/src/investia/tools/forecast.py` | nouveau : `GetForecastTool` |
| `backend/src/investia/tools/__init__.py` | param `forecaster=None` + câblage |
| `backend/src/investia/config.py` | `timestral_model`, `timestral_base_url` |
| `backend/src/investia/main.py`, `cli.py` | construction du forecaster si clé Mistral |
| `backend/src/investia/agent/prompts.py` | 1 ligne system prompt |
| `backend/tests/test_forecast.py` | tests TDD (MockTransport) |
| `.env.example`, `docs/STATUS.md` | config + suivi |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_forecast.py tests/test_tools_registry.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/market/forecast.py src/investia/tools/forecast.py tests/test_forecast.py && uv run ty check src/investia/market src/investia/tools
# live (une fois, clé VPS) : curl de vérification du schéma de réponse /v1/forecast
```

## Hors périmètre

- Covariables known-future (jours fériés, calendrier de résultats), séries multivariées.
- Hébergement local des poids (CPU) — l'API suffit ; piste « on-prem » notée dans la veille.
- Cache des prévisions, colonne dédiée en base, UI dashboard dédiée, eval mock dédié.
- Changement de modèle par défaut (on reste sur 209M, le plus benchmarké).
