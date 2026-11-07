# Spec — 4.3 : Squelette du dashboard (React 19 + Vite + TanStack)

*Écrite le : 2026-10-31 | Étape roadmap : 4.3 | Statut : validée*

## Objectif

Le dossier `dashboard/` démarre en local (`npm run dev`), avec **4 pages routées** (Marché, Portefeuille, Agent, Traces — doc 05), un layout commun, et la page Portefeuille connectée à l'API backend (`GET /portfolio`). Le build passe et les tests Vitest passent. Le contenu riche (SSE, AG-UI, graphiques réels) arrive aux étapes 4.4/4.5.

## Pourquoi

Doc 05 : 4 pages, React 19 + Vite + TanStack (P2 validée). On pose le squelette propre avant de brancher le temps réel.

## Contraintes

- Stack (P2) : **React 19 + Vite + TanStack Router + TanStack Query + Tailwind CSS + lightweight-charts + Zustand**, TypeScript strict. Gestionnaire : **npm** (rien d'autre n'existe dans le projet frontend).
- 4 routes : `/marche`, `/portefeuille`, `/agent`, `/traces` (+ redirect `/` → `/marche`). Layout avec nav clavier-accessible (liens `<a>`, focus visible).
- `src/api.ts` : client API vers le backend (base URL via `import.meta.env.VITE_API_URL`, défaut `http://127.0.0.1:8000`), TanStack Query pour `GET /portfolio`.
- Page Portefeuille : affiche cash, positions, valeur totale depuis l'API ; état de chargement et **erreur lisible** si l'API est down (jamais de page blanche).
- Page Marché : graphique lightweight-charts avec données **mock** locales (`src/lib/mockMarket.ts`) pour l'instant.
- Pages Agent et Traces : placeholder clair (« arrive à l'étape 4.4/4.5 »).
- Aucune clé API côté client ; toutes les données passent par le backend.
- Bandeau permanent « Simulation — argent fictif » (doc 05).
- Tests : Vitest + Testing Library — le routeur rend les 4 pages, la page portefeuille affiche la valeur mockée, l'erreur API s'affiche lisiblement.
- CI : nouveau job `frontend` (npm ci + lint + build + test) dans `.github/workflows/ci.yml`.
- Accessibilité de base : labels, contrastes, navigation clavier (doc 05).

## Critères d'acceptation

- [ ] `cd dashboard && npm run build` passe (TypeScript strict, zéro erreur).
- [ ] `cd dashboard && npm test` passe (4+ tests : routage, portefeuille mock, erreur API).
- [ ] `npm run dev` démarre ; `/`, `/marche`, `/portefeuille`, `/agent`, `/traces` répondent.
- [ ] La page portefeuille affiche la valeur totale mockée via TanStack Query.
- [ ] Le graphique lightweight-charts se rend sur /marche (données mock).
- [ ] Le bandeau « Simulation — argent fictif » est visible sur toutes les pages.
- [ ] La CI GitHub fait aussi lint+build+test du frontend (job `frontend` vert).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `dashboard/package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.ts` | création (stack P2) |
| `dashboard/src/main.tsx`, `App.tsx`, `api.ts` | création : router + client API |
| `dashboard/src/components/Layout.tsx` | création : layout + nav + bandeau simulation |
| `dashboard/src/pages/Marche.tsx`, `Portefeuille.tsx`, `Agent.tsx`, `Traces.tsx` | création : 4 pages |
| `dashboard/src/lib/mockMarket.ts` | création : données mock marché |
| `dashboard/src/components/PriceChart.tsx` | création : graphique lightweight-charts |
| `dashboard/src/__tests__/*.test.tsx` | création : tests Vitest/RTL |
| `.github/workflows/ci.yml` | modification : job frontend |
| `dashboard/.gitignore` | création : node_modules, dist |

## Comment vérifier

```bash
cd dashboard && npm install && npm run build && npm test
npm run dev   # puis ouvrir http://localhost:5173
```

## Hors périmètre

SSE temps réel (4.4), AG-UI chat (4.4), outil get_portfolio dans l'agent (4.5), Authelia (4 bis), Vite proxy vers le backend en dev (optionnel, via VITE_API_URL).
