# Spec 23f — streamdown (markdown streaming) + SSE replay Last-Event-ID

*Écrite le : 15/11/2026 | Étape veille D94 (chantier 23 suite) | Statut : validée le 15/11/2026*

## Objectif

Deux améliorations front/back du chat agent : (1) les réponses de l'agent sont rendues
en **markdown streamé** (listes, tableaux, blocs de code) via `streamdown`, sans changer
la DA ; (2) un stream SSE coupé (réseau, refresh) **reprend sans perdre d'événement** grâce
au `Last-Event-ID` (replay depuis la base + repli par polling).

## Pourquoi

Aujourd'hui `Agent.tsx:548` affiche `msg.answer` en texte brut (`whitespace-pre-wrap`) :
les réponses structurées de l'agent (listes, tableaux) sont illisibles. Et si le flux SSE
tombe, les événements perdus ne sont jamais renvoyés (le client relance un run neuf ou
perd la fin). Veille D94 : streamdown 2.7.1 + SSE replay Last-Event-ID.

## Contraintes

- Zéro régression : protocole `legacy` par défaut inchangé côté format d'event ; `agui`/`a2ui`
  non touchés par le replay (hors périmètre). `format_sse` gagne un `id:` optionnel
  (rétrocompatible, défaut None).
- Sécurité : `run_id` de reprise validé (format UUID) ; aucun secret ; payloads déjà
  redactés en amont (13a/23e).
- Dépendance : une seule, `streamdown@2.7.1` (Vercel, MIT, pinnée exacte dans
  `dashboard/package.json`) — validée par le choix de ce chantier. Pas de `react-markdown`.
- DA inchangée : le composant markdown remplace le contenu du même conteneur, mêmes classes.
- ⚠️ `run_events` grossit avec les runs (payloads JSONB) — pas de rétention en v1 (noté).

## Contrat détaillé

### Backend

1. Migration **0013** : `run_events(run_id TEXT, seq INTEGER, event TEXT, payload JSONB,
   created_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (run_id, seq))` + index sur run_id.
2. `investia/sse.py` : `format_sse(event, payload, event_id: int | None = None)` →
   `id: <seq>\nevent: ...\ndata: ...\n\n` quand event_id est fourni.
3. `tracing/store.py` : protocole + `DbTraceStore` gagnent
   `append_event(run_id, seq, event, payload)` et `events_after(run_id, last_seq) -> list[dict]`.
4. `POST /agent/run` : `AgentRunBody` gagne `run_id: str | None = None` ; header
   `Last-Event-ID` lu. Deux modes :
   - **nouveau run** (run_id absent) : comportement actuel + wrapper du sink qui persiste
     chaque event (seq croissant à partir de 1, run_id lu dans le payload de l'event
     `start`) et émet `id: <seq>` en protocole legacy ;
   - **replay** (run_id présent) : valide le format UUID (422 sinon), 404 si run inconnu ;
     stream les events stockés avec `seq > Last-Event-ID` (0 si absent) dans l'ordre,
     avec leur `id:` ; puis si le run est terminé → fin du stream ; si le run est encore
     actif → event `detached {"run_id": ...}` puis fin (le client repliquera en polling
     `GET /traces/{run_id}`).

### Frontend (dashboard)

5. `streamdown@2.7.1` ajouté (dep pinnée) ; nouveau `src/components/Markdown.tsx`
   (`<Streamdown>{children}</Streamdown>`) utilisé à la place du texte brut pour
   `msg.answer` dans `Agent.tsx` (mêmes classes de conteneur).
6. `src/lib/sse.ts` : `SseParser` parse aussi les lignes `id:` → `SseEvent.id` ;
   `streamSse` suit le dernier id reçu et l'expose (callback `onEvent(event, data, id)`).
7. `src/api.ts` : `streamAgentRun(question, onEvent, signal, protocol, resume?)` avec
   `resume = { runId, lastEventId }` → body `{question, run_id}` + header `Last-Event-ID`.
8. `src/pages/Agent.tsx` : sur erreur réseau du stream (hors abort volontaire), retry
   automatique max 3 (backoff 1 s / 2 s / 4 s) avec `resume` (run_id lu dans l'event
   `start`, lastEventId suivi) ; sur event `detached`, poll `GET /traces/{run_id}`
   toutes les 2 s jusqu'au statut final, puis affichage normal.

## Critères d'acceptation

- [ ] Backend : `uv run pytest -q -m "not integration"` vert (nouveaux tests TDD :
  `format_sse` avec id, persistance seq, replay `seq > last`, 404 run inconnu,
  422 run_id invalide, run actif → `detached`, nouveau run inchangé).
- [ ] `uv run ruff check .` / `ruff format --check .` / `ty check` propres.
- [ ] Dashboard : `npm test` (parser `id:`, retry avec Last-Event-ID, rendu Streamdown),
  `npm run lint`, `npm run build` verts.
- [ ] Comportement observable : run terminé → re-POST `/agent/run` avec `run_id` +
  `Last-Event-ID: 2` renvoie exactement les events de seq 3..N avec leur `id:`.
- [ ] Le chat agent affiche le markdown (liste/tableau) de la réponse, DA inchangée.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/sse.py` | `format_sse(..., event_id=None)` |
| `backend/src/investia/tracing/store.py` | `append_event` / `events_after` (+ protocole) |
| `backend/src/investia/main.py` | body.run_id, header Last-Event-ID, wrapper sink, branche replay |
| `backend/alembic/versions/0013_run_events.py` | création |
| `backend/tests/...` | tests TDD replay + format_sse id |
| `dashboard/package.json` | `streamdown@2.7.1` |
| `dashboard/src/components/Markdown.tsx` | création (Streamdown) |
| `dashboard/src/lib/sse.ts` | parse `id:`, lastEventId |
| `dashboard/src/api.ts` | `resume` dans streamAgentRun |
| `dashboard/src/pages/Agent.tsx` | retry/reconnect + Streamdown + poll sur detached |
| `dashboard/src/__tests__/...` | tests parser/retry/rendu |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
cd dashboard && npm test && npm run lint && npm run build
```

## Hors périmètre

- Replay/ids sur `/api/agents/run` (multi-agents) et protocoles agui/a2ui — v2.
- Live attach d'un run encore actif (Redis pub/sub) — v1 se contente de replay + `detached` + polling.
- Rétention/purge de `run_events`.
- streamdown sur les autres pages (Traces, etc.).
