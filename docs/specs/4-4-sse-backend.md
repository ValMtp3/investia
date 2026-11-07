# Spec — 4.4a : Backend SSE (agent run + marché temps réel)

*Écrite le : 2026-10-31 | Étape roadmap : 4.4a | Statut : validée*

## Objectif

Deux flux **SSE** (Server-Sent Events, D14) côté backend, zéro dépendance ajoutée (StreamingResponse FastAPI) :

1. `POST /agent/run` — stream les événements de la boucle d'agent en direct.
2. `GET /market/stream?symbols=AAPL,SAP.DE` — pousse les prix des actifs toutes les 5 s.

Le frontend (4.4b) consomme ces flux.

## Pourquoi

Doc 05 : SSE, le serveur pousse, le client ne poll jamais. Le chat agent doit montrer les appels d'outils en direct (AG-UI plus tard, SSE maison maintenant — D41 : fait main).

## Contraintes

- Format SSE standard : `event: <kind>\ndata: <json>\n\n`. Kinds agent : `start`, `llm_call`, `tool_call`, `guardrail`, `answer`, `error`, `done`. Kinds marché : `quotes`, `error`.
- `run_agent` gagne un paramètre optionnel `event_sink: (kind, payload) -> Awaitable[None]`. La boucle émet à chaque étape (déjà logguée côté traces). Le CLI passe un sink console (affiche les étapes en direct).
- `POST /agent/run` body `{question: str, max_turns?: int}` → `StreamingResponse(media_type="text/event-stream")` : crée une queue asyncio, lance `run_agent` en tâche avec un sink qui push dans la queue, yield les events jusqu'à `done`/`error`. Gère la déconnexion client (annule la tâche).
- `GET /market/stream?symbols=A,B` → boucle toutes les 5 s : `market.get_quote` pour chaque symbole (cache Redis 60 s côté service), yield `event: quotes`. S'arrête à la déconnexion.
- Erreurs → `event: error` avec message lisible, puis `done`.
- Sécurité : aucune clé dans les événements.
- Tests : httpx ASGI client en streaming (`client.stream`) — vérifie la séquence d'événements SSE pour un run mocké ; test du stream marché (2 événements puis cut). TDD.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_sse_*`).
- [ ] `POST /agent/run` (mock LLM+market) → flux SSE contient dans l'ordre : start, llm_call, tool_call, guardrail, answer, done.
- [ ] La réponse finale `answer` contient le texte complet ; `done` contient le récap (tours, coût).
- [ ] `GET /market/stream?symbols=AAPL` → au moins 2 événements `quotes` avec prix + source + horodatage, espacés.
- [ ] Erreur (question vide / outil en panne) → `event: error` lisible puis `done`.
- [ ] CLI inchangée (sink console optionnel, pas de SSE).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/loop.py` | modification : `event_sink` optionnel, émission à chaque étape |
| `backend/src/investia/sse.py` | création : helpers SSE (format event, StreamingResponse) |
| `backend/src/investia/main.py` | création des routes `POST /agent/run`, `GET /market/stream` |
| `backend/src/investia/cli.py` | modification : sink console |
| `backend/tests/test_sse.py` | création : flux agent + marché en streaming (mock) |

## Comment vérifier

```bash
cd backend && uv run pytest -q
# live : curl -N -X POST localhost:8000/agent/run -d '{"question":"prix AAPL ?"}'
#        curl -N "localhost:8000/market/stream?symbols=AAPL"
```

## Hors périmètre

Frontend (4.4b), AG-UI/CopilotKit (remplace le SSE maison plus tard si besoin), auth sur ces routes (4 bis).
