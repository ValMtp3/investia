# Spec — 1.1 : Connecteurs de données + cache Redis

*Écrite le : 2026-10-31 | Étape roadmap : 1.1 | Statut : validée*

## Objectif

Pouvoir demander un prix, un historique, une news ou un taux de change à une source fiable, avec un cache Redis pour respecter les limites des API gratuites.

## Pourquoi

L'agent calculera sur des données réelles (étape 1.2/1.4). Sans connecteurs propres et sans cache, on grille les quotas gratuits (Finnhub : 60 appels/min) et on obtient des chiffres sans source. D28, P8, D15.

## Contraintes

- Un **connecteur par source**, derrière une interface commune (`Protocol`) : changer de fournisseur ne touche pas le reste du code.
- **Format commun** pour toute donnée : `valeur`, `devise`, `source`, `horodatage`, `delayed` (booléen). Jamais de chiffre sans source.
- **Cache Redis avec TTL** : prix 60 s, historique 1 h, news 15 min, taux 1 jour.
- Sources (P8) : **Finnhub** (US temps réel + news US, clé), **Yahoo Finance chart** (Europe, sans clé), **CoinGecko Demo + Binance public** (crypto), **Frankfurter/ECB** (taux, sans clé).
- Clés API en variables d'environnement (`Settings`), jamais en dur.
- Erreur fournisseur → exception claire avec le nom de la source ; **jamais de valeur fabriquée**.
- Tests unitaires sans réseau (réponses HTTP mockées) ; tests réels marqués `@pytest.mark.integration`.
- TDD : test rouge → code minimal → vert.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris les nouveaux `test_market_*`).
- [ ] `get_quote("AAPL")` (fixture Finnhub mockée) → `MarketData` avec `source="finnhub"`, `devise="USD"`, horodatage récent.
- [ ] `get_quote("SAP.DE")` (fixture Yahoo mockée) → `source="yahoo"`, `devise="EUR"`.
- [ ] Deux appels `get_quote("AAPL")` à la suite → **1 seul appel HTTP** (le 2e vient du cache Redis).
- [ ] Fournisseur en panne (mock 500) → exception claire, aucune donnée renvoyée.
- [ ] `test_secrets_hygiene.py` toujours vert (aucune clé en dur dans le code).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/market/base.py` | création : `MarketData`, `Protocol MarketDataConnector` |
| `backend/src/investia/market/finnhub.py`, `yahoo.py`, `coingecko.py`, `frankfurter.py` | création : un connecteur par source |
| `backend/src/investia/market/router.py` | création : choisit la source selon le symbole (.DE/.PA → Yahoo, US → Finnhub, crypto → CoinGecko, taux → Frankfurter) |
| `backend/src/investia/market/cache.py` | création : cache Redis TTL générique |
| `backend/tests/test_market_*.py` | création : tests mockés + intégration |

## Comment vérifier

```bash
cd backend && uv run pytest -q                       # tout vert
TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration   # tests réels
```

## Hors périmètre

Boucle d'agent, outils exposés au LLM, portefeuille, news Europe, MCP. Pas de stockage en PostgreSQL (le cache suffit à cette étape).
