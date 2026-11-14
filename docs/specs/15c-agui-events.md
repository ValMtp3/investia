# Spec — 15c : émettre les événements AG-UI 1.0 sur le flux SSE de /agent/run

*Écrite le : 14/11/2026 | Étape roadmap : 15 (P9 protocoles) | Statut : terminée le 14/11/2026 (529 tests non-integration passed / 1 skip, ruff/ty/format propres)*

## Objectif

Permettre au dashboard (ou à tout client AG-UI) de consommer le flux SSE de `POST /agent/run` au **vocabulaire AG-UI 1.0** via un paramètre `?protocol=agui`, sans casser le flux legacy actuel (défaut inchangé).

## Pourquoi

Veille 14/11/2026 (briques 9/10) : AG-UI 1.0 est le standard ouvert de streaming agent→UI (17k★, multi-SDK, HITL/subagents natifs). Notre transport SSE reste ; on mappe nos événements internes vers la taxonomie AG-UI avec le SDK PyPI `ag-ui-protocol` 1.0.0 (déjà ajouté, module `ag_ui.core`), qui garantit la conformité (les events sont des modèles pydantic sérialisés `data: {"type": ...}`).

## Contraintes

- Nouveau module `backend/src/investia/agent/agui.py` : `to_agui_events(kind, payload) -> list[BaseEvent]`.
  Mapping : `start` → `RunStartedEvent(thread_id=run_id, run_id=run_id, input=question)` ; `answer` → `TextMessageStart` + `TextMessageContent(delta=text)` + `TextMessageEnd` (message_id stable par run) ; `tool_call` → `ToolCallStart(tool_call_id, tool_call_name)` + `ToolCallArgs(delta=json args)` ; `done` → `RunFinishedEvent(thread_id, run_id, result={status, turns, cost_cents})` ; `llm_call`, `guardrail`, `injection`, `approval_request`, `approval`, `plan`, `reflection`, `consensus`, `cache_hit` → `CustomEvent(name=kind, value=payload)` ; erreur → `RunErrorEvent(message)`.
- `POST /agent/run` gagne `protocol: Literal["legacy", "agui"] = "legacy"` (query param). En mode `agui`, le flux émet `data: {"type": "RUN_STARTED", ...}\n\n` (pas de champ `event:`). Mode legacy = octets identiques à aujourd'hui.
- La boucle `run_agent` n'est PAS modifiée (mapping dans le sink, côté `main.py`).
- Zéro régression : `test_sse.py` et le dashboard (legacy) inchangés.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_agui.py -q` passe : mapping unitaire de chaque kind (types AG-UI attendus, champs remplis) ; les events émis valident contre les modèles `ag_ui`.
- [ ] Test API : `POST /agent/run?protocol=agui` (LLM fake) → le flux contient `"type": "RUN_STARTED"`, `TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START`, `"type": "RUN_FINISHED"`, et AUCUNE ligne `event:` legacy. Sans le param → flux legacy inchangé.
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty/format propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/agui.py` | nouveau : `to_agui_events` (modèles `ag_ui.core.events`) |
| `backend/src/investia/main.py` | param `protocol` sur `/agent/run` (+ orchestrateur multi-agents si même pattern, voir hors périmètre), sink traduit en AG-UI si demandé |
| `backend/tests/test_agui.py` | tests TDD |
| `backend/pyproject.toml` | `ag-ui-protocol` 1.0.0 (validé) |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_agui.py tests/test_sse.py -q
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

Adoption du client `@ag-ui/client` côté dashboard (migration progressive du front, chantier ultérieur), `subagentRunId` pour tracer quel agent A2A parle (15d éventuel), resumable streams (Last-Event-ID + replay depuis run_steps — veille brique 10), protocole sur l'orchestrateur A2A (`/api/agents/run`).
