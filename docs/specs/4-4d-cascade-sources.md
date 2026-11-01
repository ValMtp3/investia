# Spec — 4.4d : Cascade de sources de données (plan B, plan C)

*Écrite le : 2026-11-01 | Étape roadmap : 4.4d (suite de 4.4c) | Statut : terminée le 2026-11-01, sauf la vérification réelle de Twelve Data et Massive (clés non créées)*

## Objectif

Quand la source principale d'un cours tombe (ex. Yahoo en HTTP 429), le backend essaie automatiquement la source suivante au lieu d'échouer. L'historique d'AAPL s'affiche même si Yahoo bloque, et la carte SAP.DE montre sa dernière clôture, clairement étiquetée, au lieu d'« erreur ».

## Pourquoi

Constat du 2026-11-01 sur le vrai backend : Yahoo répond 429 depuis le conteneur, donc AAPL n'a pas de courbe et SAP.DE n'a pas de prix en direct. Doc 04 prévoit déjà une « stratégie multi-sources ». Décision du propriétaire : cascade avec EODHD, Twelve Data et Massive, sources gratuites même peu fiables, cumulées pour fiabiliser. Modifie la décision P8 (routage des sources) : à noter en D46.

## Contraintes

- **Jamais de chiffre inventé** (doc 04) : chaque donnée garde sa vraie source, sa devise et sa date ; une clôture de la veille n'est jamais présentée comme un prix du jour.
- **Pas de contournement d'anti-robot** : aucun faux `User-Agent`, aucun scraping de Stooq. Uniquement des API à clé gratuite et le connecteur Yahoo tel qu'il est.
- Zéro dépendance Python ajoutée (`httpx` déjà là). Les clés viennent de `.env` (`TWELVEDATA_API_KEY`, `MASSIVE_API_KEY`), jamais dans le code ni git. Un connecteur n'existe que si sa clé est présente (comportement actuel).
- Quotas gratuits : EODHD 20 appels/jour (partagés SAP.DE + AAPL…), Twelve Data 800 crédits/jour, Massive 5 appels/min. Donc **cache de l'historique porté à 24 h** (une clôture ne change qu'une fois par jour).
- Ne pas casser : `pick_source` existant et ses tests, l'outil `get_quote`/`get_history` de l'agent, la valorisation du portefeuille, le format de `/market/history` et `/market/stream` (champs **ajoutés** seulement).
- Le **repli « dernière clôture » ne s'applique qu'à l'affichage** (route `/market/stream`), pas au `get_quote` utilisé par l'agent et le portefeuille : ils gardent l'erreur claire plutôt qu'un prix de la veille pris pour un prix du jour.

## Ordre des sources (cascade)

| Besoin | Sources essayées, dans l'ordre |
|---|---|
| Historique actions US (AAPL) | yahoo → eodhd → twelvedata → massive |
| Historique Europe (SAP.DE) | eodhd (inchangé, pas d'alternative gratuite fiable) |
| Historique crypto / change | coingecko / frankfurter (inchangé) |
| Prix en direct (quote) | inchangé : une seule source par symbole |
| Prix affiché SAP.DE si Yahoo échoue | dernière clôture de l'historique EODHD, avec `is_close: true` et sa date |

Une source **non configurée** (pas de clé) est sautée et mentionnée dans l'erreur finale. Si toutes échouent : erreur 502 listant chaque tentative, ex. `AAPL: yahoo: HTTP 429 (en pause) · eodhd: HTTP 404 · twelvedata: non configuré · massive: non configuré`.

## Critères d'acceptation

- [ ] `MarketDataError` gagne un champ `rate_limited` (faux par défaut) ; le connecteur Yahoo le met à vrai sur HTTP 429.
- [ ] **Cascade** : si la 1re source lève `MarketDataError`, la 2e est essayée, et ainsi de suite ; le résultat porte la `source` de celle qui a répondu. Tests avec de faux connecteurs : 1re OK → les autres ne sont pas appelées ; 1re KO + 2e OK → résultat de la 2e ; toutes KO → erreur listant chaque tentative ; source non configurée → sautée.
- [ ] **Pause après 429** : une source qui a répondu `rate_limited` est mise en pause 10 min (clé Redis `cooldown:<source>`, TTL 600 s) ; pendant la pause elle n'est pas appelée (« en pause » dans l'erreur). Test avec Redis simulé.
- [ ] **Cache 24 h** pour l'historique (`TTL_HISTORY = 86400`), une erreur n'est jamais mise en cache.
- [ ] **EODHD pour les US** : `AAPL` → `AAPL.US`, devise `USD` ; `SAP.DE` → `SAP.XETRA`, `EUR` (inchangé) ; les tests existants d'EODHD passent sans modification.
- [ ] **Nouveaux connecteurs** `TwelveDataConnector` et `MassiveConnector` (historique US en clôtures journalières ; quote et news → erreur claire « non supporté »), testés avec des réponses simulées (`httpx.MockTransport`) ; tests d'intégration réels ignorés sans clé, comme `test_market_integration.py`. L'URL et le format exacts de chaque API sont **relus dans la doc officielle avant d'écrire le connecteur** (Context7 / pages officielles), pas écrits de mémoire.
- [ ] **Repli d'affichage SAP.DE** : si le prix en direct d'un symbole échoue dans `/market/stream`, la route essaie la dernière clôture de l'historique et l'envoie avec `is_close: true`, `delayed: true` et le `timestamp` de la clôture ; si ça échoue aussi, l'erreur actuelle est conservée. Test : prix KO + historique OK → quote avec `is_close: true`.
- [ ] **Dashboard** : une carte avec `is_close` affiche « clôture du 30/10 » (date, pas d'heure) à la place de « 00:00 · eodhd » ; test dans `Marche.test.tsx`. La légende du graphique affiche la source qui a répondu.
- [ ] `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run ty check` passent ; `cd dashboard && npx vitest run && npx tsc --noEmit && npm run build` passent.
- [ ] Vérification réelle : backend Docker reconstruit ; `curl '/market/history?symbol=AAPL'` renvoie des points (source `eodhd` tant que Yahoo est bloqué) ; la page Marché trace AAPL et affiche SAP.DE en clôture étiquetée. Twelve Data et Massive vérifiés en vrai seulement quand les clés sont dans `.env`.
- [ ] `docs/04-donnees-de-marche.md` (tableau + stratégie multi-sources), `docs/09-decisions.md` (D46), `docs/STATUS.md` mis à jour ; `.env.example` (à la racine du repo) documente les deux nouvelles clés (sans valeur).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/market/base.py` | `MarketDataError.rate_limited` |
| `backend/src/investia/market/router.py` | `pick_sources(symbol, kind)` (liste ordonnée) ; `pick_source` reste (1re de la liste) |
| `backend/src/investia/market/service.py` | cascade, pause après 429, `TTL_HISTORY` 24 h |
| `backend/src/investia/market/yahoo.py`, `eodhd.py` | `rate_limited` sur 429 ; EODHD : symboles et devise US |
| `backend/src/investia/market/twelvedata.py`, `massive.py` | création des connecteurs |
| `backend/src/investia/market/__init__.py`, `config.py` | branchement des 2 connecteurs, 2 clés optionnelles |
| `backend/src/investia/main.py` | repli « dernière clôture » dans `/market/stream` |
| `backend/tests/test_market_*.py` | tests cascade, pause, connecteurs, repli |
| `dashboard/src/api.ts`, `pages/Marche.tsx`, `__tests__/Marche.test.tsx` | `is_close`, affichage « clôture du … » |
| `docs/04-…`, `docs/09-decisions.md`, `docs/STATUS.md`, `.env.example` | documentation |

## Comment vérifier

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run ty check
cd dashboard && npx vitest run && npx tsc --noEmit && npm run build
cd deploy && docker compose --env-file ../.env up -d --build backend
curl -s 'http://127.0.0.1:8000/market/history?symbol=AAPL&days=30' | head -c 300
```

## Risques connus

- ⚠️ **EODHD gratuit = 20 appels/jour**, un 404 compte. Le cache de 24 h garde ça à environ 1 appel par symbole et par jour ; sans lui le quota serait vite épuisé.
- ⚠️ Yahoo peut aussi bloquer l'historique d'AAPL pendant des jours : EODHD devient alors la source réelle (1 an d'historique seulement, plafond du plan gratuit).
- ⚠️ Twelve Data : le plan gratuit donne-t-il les clôtures journalières US ? Non confirmé par la doc → un appel de test dès que la clé existe.
- ⚠️ Deux sources peuvent donner des clôtures légèrement différentes (ajustement des dividendes) : la courbe peut changer de légère façon quand la source change ; la légende nomme toujours la source.

## Hors périmètre

Sources payantes, Binance en secours crypto, alertes quand une source tombe, historique intraday, choix de la période dans l'interface, repli « dernière clôture » pour l'agent et le portefeuille.
