# Spec — 9 : Observabilité OTel GenAI (spans `gen_ai.*` vers PostgreSQL)

*Écrite le : 2026-11-07 | Étape roadmap : 9 | Statut : terminée (2026-11-07)*

## Objectif

Chaque appel LLM et chaque appel d'outil émet un **span OpenTelemetry GenAI** (`gen_ai.*`, standard 2026), exporté vers **PostgreSQL** (D38) dans une table `otel_spans`, lié au `run_id` courant, et affiché dans la page `/traces` (durée, modèle, tokens, coût, erreur).

## Pourquoi

`docs/03-harness.md` §7 : « spans OpenTelemetry GenAI (`gen_ai.*` — le standard 2026). Comme la boîte noire d'un avion : en cas d'erreur, on rejoue ce qui s'est passé. » Noté « 2.3 en attente » dans STATUS. D38 : export PostgreSQL d'abord, Langfuse plus tard si besoin.

## Contraintes

- **Une dépendance ajoutée avec accord** : `opentelemetry-sdk` (API officielle + SDK + exporter custom vers PostgreSQL). Pas de Langfuse pour l'instant (D38).
- Attributs sémantiques standard : `gen_ai.operation.name=chat`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.model`, `gen_ai.request.temperature`, `error.type` en cas d'échec. Pour les outils : span `tool.call` avec `gen_ai.tool.name` / `gen_ai.tool.arguments` (tronqués) / durée / ok.
- Lien au run : `contextvars.ContextVar` `current_run_id` posé par `run_agent`, lu par l'exporter → colonne `run_id` dans `otel_spans`. Sans run (CLI hors run) → `run_id` NULL.
- Migration Alembic : table `otel_spans` (span_id PK, run_id FK nullable, parent_span_id, name, start_ts, end_ts, attributes JSONB, status, error). Index sur (run_id).
- Zéro régression : sans OTel configuré (tests), le code marche comme avant (exporter no-op). Aucun secret dans les attributs (jamais de contenu de prompt complet — juste longueurs ; arguments d'outils tronqués à 200 car. comme run_steps).
- La page `/traces` affiche les spans du run sélectionné (liste chronologique : opération, modèle/outil, durée, tokens, statut).
- Tests d'abord ; `uv run pytest -q -m "not integration"` + ruff + ty verts ; dashboard : vitest + lint + build verts.

## Critères d'acceptation

- [x] `uv add opentelemetry-sdk` ; migration Alembic `otel_spans` appliquée (`alembic upgrade head` → `0006_otel_spans (head)`, vérifié sur la base locale : colonne `run_id UUID` + FK vers `runs(id)`).
- [x] `backend/src/investia/tracing/otel.py` : `init_otel(session_factory)` (TracerProvider + `_Dispatcher` à exporter remplaçable à chaud + `PgSpanExporter`) ; spans no-op sans init. Le span `gen_ai.chat` (`start_chat_span`) est posé dans la **boucle** (`agent/loop.py`, autour de `llm.chat`) plutôt que dans `LlmClient.chat` — il englobe ainsi aussi les métadonnées de coût du run ; span `tool.call` (`start_tool_span`) dans `_execute_tool`.
- [x] Un run produit des spans en base : test avec LLM fake + outil fake (`test_otel.py`) → 2 spans chat (avec gen_ai.request.model, usage tokens, cost) + 1 span tool.call, tous avec le bon run_id. Vérifié aussi de bout en bout contre la base locale : 3 lignes dans `otel_spans` liées au `run_id` du run.
- [x] `GET /traces/{run_id}` renvoie aussi `spans: [...]` (name, start_ts/end_ts, attributes, status, error ; table absente tolérée → liste vide).
- [x] Page `/traces` : section « Spans OTel » sous le détail du run (liste chronologique : heure, nom, badge statut, durée, type d'erreur, attributs JSON).
- [x] Sans run_id (hors run) : spans avec run_id NULL, pas de crash (`test_no_run_id_means_null_not_crash`).
- [x] Erreur LLM → span avec status ERROR + `error.type`, pas d'exception (`test_llm_error_marks_span_error`).
- [x] `uv run pytest -q -m "not integration"` (288 passed), ruff, ruff format, ty, `npx vitest run` (102 passed), `npm run lint && npm run build` verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/pyproject.toml` / `uv.lock` | `opentelemetry-sdk` |
| `backend/alembic/versions/0xxx_otel_spans.py` | migration table otel_spans |
| `backend/src/investia/tracing/otel.py` | création : provider + exporter PG + spans |
| `backend/src/investia/llm/client.py` | span chat autour de l'appel |
| `backend/src/investia/agent/loop.py` | span tool.call + ContextVar run_id |
| `backend/src/investia/tracing/store.py` | `get_run` inclut les spans |
| `backend/src/investia/main.py` | init OTel au démarrage |
| `backend/tests/test_otel.py` | création : spans émis, run_id, erreur, no-op |
| `dashboard/src/pages/Traces.tsx` + `api.ts` + tests | section spans |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 9 |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
# migration : alembic upgrade head (base scratch)
# run avec LLM fake → SELECT count(*) FROM otel_spans WHERE run_id = ...
cd dashboard && npx vitest run && npm run lint && npm run build
```

## Hors périmètre

- Langfuse self-hosted (plus tard si besoin, D38).
- Export OTLP vers un collector externe.
- Métriques (compteurs) — juste des spans ici.
- Sampling.
