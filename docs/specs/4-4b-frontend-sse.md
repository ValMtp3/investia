# Spec — 4.4b : Frontend SSE (chat agent + marché temps réel)

*Écrite le : 2026-11-01 | Étape roadmap : 4.4b | Statut : terminée le 2026-11-01*

## Objectif

Connecter les pages **Agent** et **Marché** du dashboard aux flux SSE du backend (4.4a) : plus de données mock sur ces deux pages. L'utilisateur voit l'agent réfléchir et appeler ses outils en direct, et les prix se mettent à jour en temps réel.

## Pourquoi

Doc 05 (dashboards) : le chat agent doit montrer les étapes en direct et la page marché pousser les prix. D41 : SSE fait main, zéro dépendance ajoutée — donc le client SSE du frontend est aussi écrit à la main (fetch + ReadableStream, pas EventSource qui ne fait pas de POST).

## Contraintes

- Zéro dépendance npm ajoutée (D41). Stack existante : React 19 + Vite + TanStack Router/Query + Tailwind 4.
- Client SSE maison (`src/lib/sse.ts`) : parse `event:`/`data:` sur le `body` du `fetch`, appel via `AbortSignal` pour le bouton stop.
- Accessibilité : `aria-live="polite"` sur le flux de l'agent, `role="status"` pendant l'envoi, `role="alert"` en cas d'erreur.
- Sécurité : aucune clé côté client (déjà le cas — tout passe par le backend, `VITE_API_URL`).
- Ne pas casser : page Portefeuille, page Traces, navigation, tests existants (`App.test.tsx`, `Portefeuille.test.tsx`).
- Backend (petits fix, testés) : ajouter `"symbol"` dans chaque quote de `GET /market/stream` (le frontend a besoin de savoir quel prix va avec quel symbole) ; ajouter `CORSMiddleware` autorisant l'origin du frontend (env `FRONTEND_ORIGIN`, défaut `http://localhost:5173`) — sinon le navigateur bloque les appels 5173 → 8000 en dev.
- Le graphique de la page Marché garde ses données mock pour l'instant (historique en SSE = étape ultérieure).

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (nouveaux tests : `symbol` présent dans les quotes streamées, header CORS présent).
- [ ] `cd dashboard && npm run test` passe (nouveaux tests : parser SSE, page Agent avec flux mocké, page Marché avec flux mocké).
- [ ] `cd dashboard && npm run lint && npm run build` passent sans erreur.
- [ ] Page `/agent` : envoyer une question → les événements `tool_call` / `guardrail` / `llm_call` s'affichent au fur et à mesure, la réponse finale (`answer`) puis le récap (`done` : tours, coût) apparaissent ; le bouton « Stop » annule le flux (AbortController) ; si le réseau coupe → message lisible avec `role="alert"`.
- [ ] Page `/marche` : les prix de `AAPL`, `SAP.DE`, `BTC-USD` arrivent via `GET /market/stream` et se mettent à jour à chaque événement `quotes`, avec source, heure et badge « différé » quand `delayed: true` ; si le flux est en erreur → message lisible.
- [ ] La page Marché n'utilise plus `MOCK_QUOTES`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `dashboard/src/lib/sse.ts` | création : parser SSE + `streamSse()` sur fetch/ReadableStream |
| `dashboard/src/api.ts` | ajout : types `AgentEvent` / quote SSE + `streamAgentRun()` / `streamMarket()` |
| `dashboard/src/pages/Agent.tsx` | réécriture : chat streaming (formulaire, étapes en direct, stop, erreur) |
| `dashboard/src/pages/Marche.tsx` | modification : quotes live SSE au lieu de `MOCK_QUOTES` |
| `dashboard/src/lib/mockMarket.ts` | modification : garde `mockCandles` (graphique), supprime `MOCK_QUOTES` |
| `dashboard/src/__tests__/sse.test.ts` | création : parser (1 event, plusieurs events, champ event ignoré si absent) |
| `dashboard/src/__tests__/Agent.test.tsx` | création : flux SSE mocké → étapes + réponse affichées ; stop annule ; erreur réseau |
| `dashboard/src/__tests__/Marche.test.tsx` | création : flux quotes mocké → prix mis à jour avec source/heure |
| `backend/src/investia/main.py` | modification : `symbol` dans chaque quote du stream + `CORSMiddleware` |
| `backend/tests/test_sse.py` | modification : assertions `symbol` + CORS |

## Comment vérifier

```bash
cd backend && uv run pytest -q && uv run ruff check .
cd dashboard && npm run test && npm run lint && npm run build
# manuel : backend up (uvicorn) + cd dashboard && npm run dev → tester /agent et /marche en live
```

## Hors périmètre

Historique de cours en SSE (le graphique reste mock), AG-UI/CopilotKit, auth sur les routes, reconnexion automatique du stream marché, page Traces & evals.
