# Spec — 10 : Backtest du portefeuille simulé vs indice de référence (CW8.PA)

*Écrite le : 2026-11-08 | Étape roadmap : 10 | Statut : terminée (2026-11-08)*

## Objectif

Rejouer les **ordres simulés** du portefeuille sur l'**historique des clôtures** et comparer la courbe de valeur à un **buy & hold sur l'ETF monde CW8.PA** (Amundi MSCI World, EUR) depuis le capital initial. Affiché dans un module « Backtest » de la page `/portefeuille` (deux courbes + perf en %).

C'est la cible de `docs/05-dashboards.md` (« courbe de performance comparée à un indice de référence ») jamais livrée jusqu'ici.

## Décisions (D67, validées avec le propriétaire le 08/11/2026)

- **Indice de référence** : `CW8.PA` (ETF monde, coté en EUR → pas de conversion de devise pour la courbe de référence).
- **Date de départ** : date du **premier ajustement de capital** ; capital initial = son montant (fallback : 10 000 € à la date du premier ordre).
- **Prix d'exécution en backtest** : **clôture du jour** de l'ordre (dernier prix connu si trou), **frais 0,1 %** comme en réel (D35, même `apply_order` de `portfolio/calc.py`).
- **Conversion devise** : clôture × taux Frankfurter du jour (dernier taux connu si trou), comme `PortfolioService.price_eur`.
- **Résultat** : calculé **à la demande** (`GET /portfolio/backtest`), caché en **Redis 24 h** (même mécanisme que l'historique), rien de nouveau en base.
- **V1** : dashboard seul — **pas d'outil agent** `get_backtest` pour l'instant.

## Contrat API

`GET /portfolio/backtest` (read-only, comme `GET /portfolio`) :

```json
{
  "start_date": "2026-10-30",
  "initial_capital": 10000.0,
  "benchmark_symbol": "CW8.PA",
  "points": [
    {"date": "2026-10-30", "portfolio_value": 10000.0, "benchmark_value": 10000.0}
  ],
  "perf_portfolio_pct": 0.99,
  "perf_benchmark_pct": 10.0,
  "warnings": ["AAPL: aucune clôture le 2026-11-01, dernier prix connu utilisé"]
}
```

- `points` : un point par jour de cotation (union des calendriers des séries), du départ à aujourd'hui.
- `warnings` : trous de cotation, ordres ignorés (fonds insuffisants au prix de clôture), symboles sans historique.

## Règles du moteur (`portfolio/backtest.py`, code pur, testé sans réseau)

1. Calendrier = union des dates de clôture de toutes les séries (symboles + indice), entre `start_date` et aujourd'hui.
2. À chaque date : ajustements de capital appliqués (cash += montant), puis ordres du jour à la clôture du jour (prix EUR = clôture × taux du jour), via `apply_order` (frais 0,1 %). Ordre irréalisable au prix de clôture → ignoré + warning.
3. Valorisation : `cash + Σ quantité × prix EUR du jour` (dernier prix connu si trou).
4. Benchmark : `initial_capital × clôture_indice(jour) / clôture_indice(départ)` ; si pas de clôture au départ, premier jour connu.
5. Perf en % depuis le départ, sur le dernier point.

## Contraintes

- Zéro dépendance nouvelle (Polars déjà là si besoin, mais le moteur V1 est en pur Python — wenige données).
- Tests d'abord : moteur pur (achat/vente, frais, conversion USD→EUR, trou de cotation, ajustement intermédiaire, ordre ignoré, benchmark sans clôture au départ) ; puis route (payload validé, cache) ; puis dashboard (parser + module + états).
- Pas de secret exposé ; le calcul ne touche pas aux clés API côté client.
- `uv run pytest -q -m "not integration"` + ruff + ty verts ; dashboard : vitest + tsc + build verts.

## Critères d'acceptation

- [x] Moteur `portfolio/backtest.py` + 8 tests unitaires verts (achat/vente à la clôture, frais 0,1 %, conversion USD→EUR au taux du jour, trou de cotation → dernier prix connu, ajustement intermédiaire, ordre ignoré si fonds insuffisants, base indice = 1re clôture connue, pas de capital initial → perf 0 + warning).
- [x] `GET /portfolio/backtest` renvoie le contrat ci-dessus (read-only), caché 24 h en Redis via `cached` (Redis down = calcul direct, testé), 503 clair si l'historique de l'indice manque. Service `BacktestService` + 7 tests (route 200/503, service avec fakes, symbole sans historique → warning).
- [x] Dashboard : module « Backtest vs indice » sur `/portefeuille` — `BacktestChart` (2 séries : portefeuille plein, indice pointillé), badges perf %, « depuis le … · capital de départ », warnings listés, états chargement / erreur / « aucun ordre pour l'instant ». Parser avec garde-fous dans `api.ts`.
- [x] Tests dashboard verts (110 au total : 2 courbes tracées, perfs, état vide, 503, payload malformé) ; capture d'écran relue en dev contre le vrai backend (courbes CW8.PA réelles).
- [x] Vérifié en live : `GET /portfolio/backtest` répond avec les vraies clôtures EODHD (6 points, CW8.PA −1,80 % sur la période en base locale).
- [x] Docs : STATUS, roadmap (étape 10), D67.
- [x] Backend 303 tests, ruff, ruff format, ty verts ; dashboard 110 tests, tsc, build verts.

## Hors périmètre

- Outil agent `get_backtest` (peut venir plus tard).
- Stockage des backtests en base / historique des backtests.
- Stratégies automatiques, backtest intraday, plusieurs indices comparés.
- Rééquilibrage périodique de l'indice de référence (buy & hold simple).
