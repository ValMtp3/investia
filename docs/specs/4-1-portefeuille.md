# Spec — 4.1 : Portefeuille simulé en base + calculs en code + API

*Écrite le : 2026-10-31 | Étape roadmap : 4.1 | Statut : validée*

## Objectif

Le portefeuille simulé (10 000 € fictifs, D27) vit en PostgreSQL : tables, calculs de valorisation **en code** (jamais par le LLM), ordres simulés au dernier prix connu avec frais 0,1 % (D35), capital ajustable en mode admin. Une API FastAPI expose tout ça.

## Pourquoi

Doc 02 : tables `portfolios`, `positions`, `orders`, `capital_adjustments`. L'agent verra ce portefeuille via l'outil `get_portfolio` (étape 4.5). Zéro ordre réel, zéro conseil réel.

## Contraintes

- Migration `0005_portfolio.py` :
  - `portfolios` (id UUID, name, currency='EUR', cash NUMERIC(14,2), created_at)
  - `positions` (id, portfolio_id FK, symbol, quantity NUMERIC(18,8), avg_price NUMERIC(14,4)) — fractions autorisées
  - `orders` (id, portfolio_id FK, symbol, side 'buy'|'sell', quantity, price, fee, status='simulated', created_at)
  - `capital_adjustments` (id, portfolio_id FK, amount, reason, created_at)
- **Calculs en code** (`portfolio/service.py`) : `place_order` → prix = dernier connu via `MarketService.get_quote` (marché fermé = dernier connu, D35), frais = 0,1 % du montant, vérifie cash suffisant pour un buy, met à jour cash + position (prix moyen pondéré), enregistre l'ordre. `portfolio_value` = cash + Σ quantity × dernier prix (converti en EUR si besoin via Frankfurter).
- **API** (routes dans `main.py`) : `GET /portfolio`, `POST /portfolio/adjust` (admin), `POST /orders`, `GET /orders`. Admin = header `X-Admin-Token` == `APP_SECRET_KEY` (avant Authelia, étape 4 bis).
- Erreurs claires : cash insuffisant, symbole inconnu, quantité invalide → 400 avec message.
- TDD ; tests unitaires avec market fake, integration base (conteneur pgvector 5432), tests API via httpx ASGITransport.
- Le portefeuille par défaut est créé au démarrage (seed) s'il n'existe pas : 10 000 € cash.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_portfolio_*`).
- [ ] `alembic upgrade head` applique les 4 tables (test integration).
- [ ] Scénario vérifié à la main : buy 10 AAPL à 344.63 → frais 3.45 (0,1 %), cash = 10000 − 3446.30 − 3.45, position qty=10 avg=344.63, value = cash + 10×344.63.
- [ ] Sell partiel → cash crédité, qty diminuée, avg inchangé.
- [ ] Buy au-delà du cash → erreur claire, rien n'est écrit.
- [ ] `POST /portfolio/adjust` avec mauvais token → 401 ; avec bon token → cash ajusté + ligne dans capital_adjustments.
- [ ] `GET /portfolio` renvoie cash, positions valorisées, valeur totale, avec source/horodatage des prix.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0005_portfolio.py` | création : 4 tables |
| `backend/src/investia/portfolio/__init__.py`, `service.py` | création : calculs + ordres |
| `backend/src/investia/main.py` | modification : routes portefeuille + seed au démarrage |
| `backend/tests/test_portfolio*.py` | création : unitaires + integration + API |

## Comment vérifier

```bash
cd backend && uv run pytest -q
TEST_DATABASE_URL=... uv run pytest -q -m integration -k portfolio
curl localhost:8000/portfolio
```

## Hors périmètre

Outil `get_portfolio` pour l'agent (4.5), dashboards React (4.3), SSE temps réel (4.4), Authelia (4 bis), ordres conditionnels.
