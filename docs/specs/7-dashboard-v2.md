# Spec — Dashboard V2 : thème « salle de contrôle » + fonctionnalités (étape 7)

*Écrite le : 2026-11-07 | Étape roadmap : 7 | Statut : validée le 2026-11-07 (branche `feat/etape-7-dashboard-v2`)*

## Objectif

Transformer le dashboard de « squelette fonctionnel » en produit fini : thème sombre « salle de contrôle / instrument » (charbon profond, filets fins, un seul rouge signal qui ne s'allume que pour les décisions/erreurs) et fonctionnalités utiles manquantes, **sans aucune dépendance npm ajoutée**.

## Pourquoi

Le dashboard actuel paraît « trop léger » : surfaces toutes au même niveau, onglets rouges partout, pas de hiérarchie typographique, pas de variation %, pas d'historique des ordres. La spec `docs/05-dashboards.md` demande pourtant variation, performance, historique des ordres et ajustements. Direction validée par le propriétaire le 2026-11-07 : thème sombre + pack C (frontend + 2 endpoints read-only). Décision D64.

## Contraintes

- **Zéro nouvelle dépendance** (règle absolue AGENTS.md) : React 19, Tailwind v4, TanStack, lightweight-charts, police Noto Sans JP existante uniquement. Icônes = SVG inline si besoin.
- Clichés interdits (PRODUCT.md) : pas de néon « terminal hacker », pas de cartes SaaS arrondies, pas de glassmorphism/bento.
- Accessibilité WCAG AA : contrastes texte ≥ 4,5:1, bordures interactives ≥ 3:1, cibles tactiles ≥ 44px, skip link, focus géré après navigation, `prefers-reduced-motion` conservé.
- Textes UI en français ; bandeau « Simulation — argent fictif » permanent (texte inchangé) ; chaque chiffre garde sa source affichée ; jamais de page blanche.
- Backend : ajouts **read-only et additifs uniquement** (aucune règle métier modifiée). `GET /orders` et `GET /portfolio/adjustments` passent derrière le `location /api/` existant du nginx (préfixe retiré), aucune config nginx en plus.
- Ce qui existe ne doit pas casser : les 62 tests dashboard existants et la suite pytest servent de contrat ; on ne modifie un test que si le changement de comportement est intentionnel.
- Tests avant code (TDD) ; `npm run lint && npm test && npm run build` verts à chaque étape côté dashboard ; `uv run ruff check` + `uv run pytest` (non-integration) côté backend.

## Critères d'acceptation

Backend (read-only) :

- [x] `GET /orders?limit=50` (limit 1–200, défaut 50, 422 sinon) renvoie `{orders: [{id, symbol, side, quantity, price, fee, status, created_at}]}` triés `created_at` décroissant ; portfolio par défaut créé si absent.
- [x] `GET /portfolio/adjustments` renvoie `{adjustments: [{id, amount, reason, created_at}]}` triés décroissant.
- [x] `GET /portfolio` renvoie en plus `initial_capital` = 10 000 + somme des ajustements (champ additif, rétrocompatible).
- [x] `uv run ruff check backend` propre ; `uv run pytest backend/tests` (non-integration) vert avec les nouveaux tests écrits avant le code.

Frontend — design system :

- [ ] `index.css` expose la palette sombre (bg `#101214`, surface `#16191d`, wash `#1d2126`, rule `#2b3138`, rule-strong `#5d6670`, ink `#e8eaec`, muted `#9aa3ad`, signal `#d7261e`, on-signal `#ffffff`, signal-wash `#2a1512`, signal-ink `#ff6b62`, gain `#2fbf71`, caution `#e8b339`, caution-wash `#2a2113`, caution-ink `#f0c566`, focus `#5b8def`) ; `body` sur `bg`, sélection et scrollbars suivies.
- [ ] `chartTheme.ts` lit grille/couleurs depuis les tokens CSS (plus de hex en dur dans les pages) ; `PriceChart` en courbe area.
- [ ] Nouveaux composants testés : `PageHeader`, `Badge`, `Stat`, `EmptyState`, `Loading`, `Sparkline`.

Frontend — Layout & a11y :

- [ ] Skip link « Aller au contenu » vers `#main-content` ; focus déplacé dans `<main>` après chaque navigation ; liens nav, boutons et champs ≥ 44px de haut.
- [ ] Nav active = filet signal 2px + wash (plus de bloc plein) ; sidebar `bg-surface` avec attribution des sources de données en pied ; bandeau simulation restylé (texte inchangé).

Frontend — pages :

- [ ] `/marche` : watchlist de 7 symboles (AAPL, SAP.DE, BTC-USD + MSFT, NVDA, ETH-USD), variation % du jour colorée (calculée depuis l'historique), sparkline SVG par carte, sélecteur de période (5 j / 1 m / 3 m / 6 m / max → `days` 5/30/90/180/400), badge « flux en direct / interrompu », carte sélectionnée bord signal, `aria-live` déplacé sur la cellule prix de chaque carte.
- [ ] `/portefeuille` : perf depuis le départ vs `initial_capital` (€/%, colorée), plus-value latente par position (€/%), barre d'allocation cash/positions en CSS, modules « Ordres simulés » (`GET /orders`) et « Ajustements » (`GET /portfolio/adjustments`) avec états vides.
- [ ] `/agent` : suggestions de questions cliquables (remplissent le champ), bulles et étapes avec badges, focus sur le statut après Envoyer. Comportements existants (Valider/Refuser, « Voir la trace », modes solo/A2A) inchangés.
- [ ] `/traces` : badges de statut colorés, état « exécution introuvable » si `run: null`, payloads en bloc monospace, légende evals depuis les tokens.
- [x] `npm run lint`, `npm test`, `npm run build` verts dans `dashboard/` (62 tests existants + nouveaux, aucune régression).

Vérification visuelle :

- [ ] `npm run dev` + captures d'écran des 4 pages (API mockée en local) relues : hiérarchie lisible, contrastes, états d'erreur non cassés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/portfolio/service.py` | `initial_capital` dans `get_portfolio` + méthodes `list_orders`, `list_adjustments` |
| `backend/src/investia/main.py` | routes `GET /orders`, `GET /portfolio/adjustments` |
| `backend/tests/test_portfolio*.py`, `test_main_*.py` | tests écrits avant le code |
| `dashboard/src/index.css` | palette sombre `@theme`, base body/sélection/scrollbar |
| `dashboard/src/lib/chartTheme.ts` | tokens lus depuis CSS, couleurs de séries exportées |
| `dashboard/src/components/` | `Module` restylé + nouveaux `PageHeader`, `Badge`, `Stat`, `EmptyState`, `Loading`, `Sparkline` |
| `dashboard/src/components/Layout.tsx` | skip link, focus route, nav, bandeau, sidebar + attribution |
| `dashboard/src/api.ts` | `useMarketHistory(symbol, days)`, `useOrders`, `useAdjustments`, `initial_capital` + parsers |
| `dashboard/src/pages/Marche.tsx` | watchlist, variation %, sparklines, périodes, badge flux, aria-live ciblé |
| `dashboard/src/pages/Portefeuille.tsx` | perf, plus-values, allocation, ordres, ajustements |
| `dashboard/src/pages/Agent.tsx` | suggestions, badges, focus submit |
| `dashboard/src/pages/Traces.tsx` | badges statut, run null, tokens couleurs |
| `dashboard/src/__tests__/` | nouveaux tests + mises à jour intentionnelles |
| `docs/STATUS.md`, `docs/09-decisions.md` (D64), `docs/08-roadmap.md` (étape 7), `dashboard/PRODUCT.md` (direction validée) | suivi |

## Comment vérifier

```bash
# Backend
cd backend && uv run ruff check . && uv run pytest -q -m "not integration"
# Dashboard
cd dashboard && npm run lint && npm test && npm run build
# Visuel : npm run dev + captures des 4 pages contre une API mockée
```

## Hors périmètre

- Mode admin UI d'ajustement du capital (le token admin ne doit pas vivre dans le navigateur) ; courbe de performance vs indice de référence (chantier B4 séparé) ; indicateur marché ouvert/fermé (pas de calendrier côté API) ; toute nouvelle librairie ; tests E2E Playwright ; changements de règles métier.
