# Spec — 4.4c : Graphique de la page Marché avec les vrais cours

*Écrite le : 2026-11-01 | Étape roadmap : 4.4c (suite de 4.4b) | Statut : validée le 2026-11-01*

## Objectif

Le graphique de la page Marché affiche la vraie courbe des cours de clôture du symbole choisi (AAPL, SAP.DE, BTC-USD), au lieu d'une courbe inventée identique pour les trois.

## Pourquoi

La spec 4.4b a laissé le graphique sur des données mock (« historique en SSE = étape ultérieure »). Constat du propriétaire : « la courbe ne change jamais ». Doc 05 : le graphique d'un actif doit être réel. PRODUCT.md : chaque chiffre affiché indique sa source.

## Contraintes

- **Données existantes réutilisées** : `MarketService.get_history` (déjà utilisé par l'outil `get_history` de l'agent, cache Redis 1 h). Il ne donne que la **clôture journalière** (pas ouverture/haut/bas) : le graphique passe donc de bougies à une **ligne**. Sources : AAPL → Yahoo, SAP.DE → EODHD, BTC-USD → CoinGecko (`market/router.py`).
- Zéro dépendance ajoutée (`lightweight-charts` a déjà `LineSeries`, TanStack Query est déjà là).
- Sécurité : symbole validé côté backend (`^[A-Za-z0-9.\-^=]{1,20}$`), `days` borné 5 à 400 (comme l'outil), erreurs sans stack trace ni clé API.
- Honnêteté : la courbe change **une fois par jour** (clôtures), pas en continu. Les prix en direct restent dans les 3 cartes. Dit clairement dans l'interface.
- Ne pas casser : `/market/stream`, `/portfolio`, outil `get_history` de l'agent, pages Portefeuille/Agent/Traces, accessibilité (région nommée, texte alternatif).
- Pas de nouvelle table, pas de migration, pas de contrat existant modifié (route **ajoutée** seulement).

## Critères d'acceptation

- [ ] `GET /market/history?symbol=AAPL&days=30` renvoie `{symbol, source, currency, delayed, points:[{time:"YYYY-MM-DD", value}]}` ; points triés par date croissante, **un seul point par jour** (doublon → le dernier gagne : `lightweight-charts` plante sinon).
- [ ] Symbole invalide ou `days` hors 5-400 → 422. Erreur d'un fournisseur (`MarketDataError`, clé API absente) → 502 avec un message qui nomme la source, sans secret.
- [ ] `cd backend && uv run pytest -q` passe (nouveaux tests avec un faux `market` injecté : cas normal, dédoublonnage et tri, symbole invalide, `days` hors bornes, erreur fournisseur) + `ruff check` + `ruff format --check` + `ty check`.
- [ ] Page `/marche` : le graphique appelle la route pour le symbole sélectionné ; changer de symbole change la courbe ; chargement → `role="status"` « Chargement de l'historique… » ; erreur → `ErrorNotice` lisible ; liste vide → message « Aucun historique disponible pour ce symbole ».
- [ ] Sous le graphique : « Cours de clôture journaliers · source : yahoo · devise : USD » (valeurs venant de l'API) ; l'ancienne note « le graphique reste sur données mock » disparaît ; `aria-label` : « Courbe des cours de clôture de AAPL, 30 jours, source yahoo ».
- [ ] `cd dashboard && npx vitest run && npx tsc --noEmit && npm run build` passent (nouveaux tests : page Marché avec historique mocké, états chargement/erreur/vide, changement de symbole).
- [ ] Vérification réelle : avec le backend Docker reconstruit, `curl 'http://127.0.0.1:8000/market/history?symbol=AAPL'` renvoie des points réels (si une clé API manque pour un symbole : erreur claire, pas de plantage).
- [ ] `mockCandles` et `mockMarket.ts` ne sont plus utilisés : fichier supprimé (code rendu inutile par cette spec).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/main.py` | ajout de la route `GET /market/history` (+ modèle de réponse) |
| `backend/tests/test_market_history_api.py` | création : tests de la route |
| `dashboard/src/api.ts` | `useMarketHistory(symbol)` (TanStack Query) + types `MarketHistory` |
| `dashboard/src/components/PriceChart.tsx` | ligne (`LineSeries`) alimentée par les points reçus, devise et source |
| `dashboard/src/pages/Marche.tsx` | états chargement/erreur/vide, légende avec source, suppression de la note « mock » |
| `dashboard/src/lib/mockMarket.ts` | suppression |
| `dashboard/src/__tests__/Marche.test.tsx`, `App.test.tsx` | mocks `lightweight-charts` (ajout de `LineSeries`), tests historique |
| `docs/09-decisions.md`, `docs/STATUS.md` | décision (ligne au lieu de bougies, clôtures journalières) + avancement |

## Comment vérifier

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run ty check
cd dashboard && npx vitest run && npx tsc --noEmit && npm run build
cd deploy && docker compose --env-file ../.env up -d --build backend   # puis :
curl -s 'http://127.0.0.1:8000/market/history?symbol=AAPL&days=30' | head -c 400
```

## Risques connus

- ⚠️ **Devise** : l'historique de BTC-USD vient de CoinGecko en **EUR** (`vs_currency=eur`) alors que son prix en direct est en USD. La légende affiche la devise de l'historique pour ne pas mentir, mais les cartes et la courbe n'auront pas la même devise pour BTC. À régler dans une étape à part.
- ⚠️ SAP.DE passe par EODHD : sans `EODHD_API_KEY` la route répond 502 (message clair), le graphique affiche l'erreur.
- ⚠️ Yahoo n'a pas d'API officielle : si elle bloque, le graphique AAPL affiche l'erreur (même risque que pour l'agent).

## Hors périmètre

Bougies (ouverture/haut/bas/clôture), courbe intraday ou en direct, dernier point qui suit le prix live, choix de la période dans l'interface (30 jours fixes), courbe de valeur du portefeuille, réglage de la devise de BTC-USD.
