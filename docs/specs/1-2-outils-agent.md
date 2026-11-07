# Spec — 1.2 : Outils de l'agent (get_quote, get_history, get_indicators, get_news)

*Écrite le : 2026-10-31 | Étape roadmap : 1.2 | Statut : validée*

## Objectif

Quatre outils Python que l'agent pourra appeler : prix actuel, historique, indicateurs calculés en code, actualités. L'IA interprète, le code calcule (jamais l'inverse).

## Pourquoi

C'est la brique que la boucle d'agent (1.4) appellera. Un outil = fonction + schéma d'entrée strict + description pour le LLM + sortie sourcée et horodatée (doc 03, principe « le code calcule, l'IA interprète »).

## Contraintes

- Chaque outil : `name`, `description` (pour le LLM), `args_schema` (Pydantic), `async def run(...)`.
- Entrées validées par Pydantic ; symbole normalisé (majuscules).
- `get_quote`, `get_history`, `get_news` délèguent à `MarketService` (étape 1.1).
- `get_indicators` calcule **en code avec Polars** sur l'historique : moyennes mobiles 20/50 jours et volatilité annualisée 30 jours. Aucun calcul côté LLM.
- Sorties : JSON avec `source`, `horodatage`, `delayed` quand pertinent.
- Erreur de source → exception `ToolError` claire (nom de l'outil + cause), jamais de valeur fabriquée.
- Tests unitaires avec `MarketService` mocké (pas de réseau) ; TDD.
- Registre des outils : `TOOLS = {name: tool}` pour la boucle d'agent.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_tools_*`).
- [ ] `get_quote.run({"symbol": "AAPL"})` → JSON avec `value`, `currency`, `source`, `timestamp`.
- [ ] `get_indicators.run({"symbol": "AAPL", "days": 60})` sur historique fictif de 60 points → `sma20`, `sma50`, `volatility_30d_annualized` corrects (vérifiés à la main sur le fixture).
- [ ] Symbole invalide → `ToolError` nommée, pas de crash.
- [ ] Chaque outil a `name`, `description`, `args_schema` (vérifié par un test qui itère sur le registre).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/base.py` | création : `ToolError`, `BaseTool` (name/description/args_schema/run) |
| `backend/src/investia/tools/quote.py`, `history.py`, `news.py` | création : délèguent à MarketService |
| `backend/src/investia/tools/indicators.py` | création : calculs Polars (SMA20/50, volatilité annualisée) |
| `backend/src/investia/tools/__init__.py` | registre `TOOLS` + `build_tools(market_service)` |
| `backend/tests/test_tools_*.py` | création : tests avec service mocké |

## Comment vérifier

```bash
cd backend && uv run pytest -q
```

## Hors périmètre

Boucle d'agent et appels LLM (1.3/1.4), portefeuille (4.x), news Europe, MCP (étape 5).
