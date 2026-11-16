# Spec 23k — V2 replay SSE : live-attach Redis pub/sub pour un run actif + extension multi-agents

*Écrite le : 15/11/2026 | Prolonge 23f (D100) | Issu de la veille D94 (item 6/« V2 replay Redis live-attach + multi-agents ») | Statut : brouillon*

## Objectif

En 23f, un client qui renvoie `Last-Event-ID` pour un run **encore actif** reçoit
les events stockés puis un event `detached` et replie en polling `GET /traces/{id}`.
En 23k, le serveur **s'attache en direct au run** via Redis pub/sub et stream les
nouveaux events jusqu'à la fin — plus de polling côté client quand Redis est dispo.

## Pourquoi

Le polling toutes les 2 s gaspille des requêtes et ajoute de la latence. Redis est
déjà là (D33) : un canal `run:<run_id>` par run, publié par le sink qui persiste
déjà chaque event (23f). Fallback si Redis KO = comportement 23f (`detached`).

## Contrat détaillé

### 1. `backend/src/investia/sse_live.py` (nouveau)

- `channel_for(run_id: str) -> str` = `run:<run_id>`.
- `async publish_event(client, run_id, seq, kind, payload)` : `PUBLISH` un JSON
  `{seq, event, payload}` (payload déjà redacté 13a) — **erreur avalée** (log warning).
- `async live_attach(client, run_id, last_seq, idle_timeout=600)` : async generator
  qui s'abonne au canal, yield les events reçus avec `seq > last_seq` (dédup), et
  s'arrête proprement sur event final (`done`/`error`) ou après `idle_timeout` de
  silence. Si Redis est indisponible → lève `LiveAttachUnavailable`.

### 2. `main.py` — route `/agent/run` (legacy)

- Le `sink` 23f publie aussi sur Redis après `append_event` (même seq, erreur avalée).
- Mode replay (run_id + Last-Event-ID) : après le replay des events stockés, si le
  run est `running` **et** Redis OK → `live_attach` jusqu'à l'event final, puis fin
  du stream. Si Redis KO → `detached` (comportement 23f inchangé, zéro régression).

### 3. Route `/api/agents/run` (multi-agents)

- 23f était legacy-only ; 23k applique le même mécanisme (sink publish + replay avec
  live-attach) à la route multi-agents.

### 4. Frontend

- Aucun changement requis : le client envoie déjà `run_id` + `Last-Event-ID` au
  retry (23f) ; en V2 il reçoit les events live puis `done` normalement. Vérifier
  juste qu'un `done` reçu en replay termine le stream proprement (test existant).

## Critères d'acceptation

- [ ] `uv run pytest tests/test_sse_live_attach.py -q` vert (TDD, fake Redis pubsub) :
  publish appelé par le sink avec le même seq ; live_attach yield seq > last_seq,
  dédup, stop sur `done`, stop sur timeout, `LiveAttachUnavailable` si KO ;
  route replay : run running + Redis OK → events live jusqu'à done ; Redis KO → `detached`.
- [ ] Route multi-agents : même test.
- [ ] Suite complète `uv run pytest -q -m "not integration"` verte, ruff/format/ty propres.
- [ ] Dashboard : `npm test` + `npm run lint` + `npm run build` verts (inchangé ou ajusté).
- [ ] Zéro régression : sans Redis, flux 23f identique (tests 23f toujours verts).

## Hors périmètre

- Rétention/purge de `run_events` (D100, ⚠️ taille à surveiller — inchangé).
- Reprise d'un run en attente d'approbation (HITL resumable = autre chantier).
- Buffs AG-UI / protocoles agui-a2ui en live-attach (legacy + multi seulement).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/sse_live.py` | création (publish + live_attach) |
| `backend/src/investia/main.py` | sink publish + replay live-attach (legacy + multi-agents) |
| `backend/tests/test_sse_live_attach.py` | tests TDD (fake Redis) |
| `docs/STATUS.md`, `docs/09-decisions.md` (D105) | suivi |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
cd dashboard && npm test && npm run lint && npm run build
```
