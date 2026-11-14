# Spec — 16c : compaction du contexte dans `run_agent` (sliding window + résumé « untrusted » + memory flush)

*Écrite le : 14/11/2026 | Étape roadmap : 16 (mémoire & contexte) | Statut : terminée le 14/11/2026 (557 tests non-integration passed / 1 skip, ruff/ty/format propres)*

## Objectif

Quand la conversation dépasse un seuil de tokens, compacter le contexte envoyé au LLM **pendant le run** : garder le system prompt, la question, et les N derniers tours intacts, remplacer le milieu par un résumé généré par le LLM et **marqué « untrusted »** (non fiable — l'agent doit vérifier avant d'agir). Avant de jeter le vieux contexte, un *memory flush* sauvegarde les faits durables dans la mémoire longue. L'historique complet reste tracé en base (les steps `llm_call`/`tool_call` ne sont jamais supprimés).

## Pourquoi

Veille 14/11/2026 (§6, inspiré Letta / OpenClaw / LangGraph) : sans compaction, un run long finit par dépasser la fenêtre de contexte du modèle (erreur ou perte des premières instructions). La règle retenue : sliding window à ~80 % de la fenêtre, garder les N derniers tours, résumé « untrusted », historique jamais supprimé en base, memory flush avant compaction.

## Contraintes

- **Zéro régression** : `context_max_tokens=None` = compaction désactivée (comportement strictement identique). Seuil par défaut haut (100 000 tokens) pour ne jamais se déclencher sur les runs courts. `test_agent_loop.py` et toute la suite passent inchangés.
- Le résumé est inséré comme message `{"role": "system", "content": "[Résumé automatique du contexte précédent — NON FIABLE, vérifie avant d'agir] ..."}` : marqué untrusted, jamais présenté comme une instruction.
- Historique en base intact : les steps continuent d'être loggés normalement ; un step/event `compaction` est émis au moment de la compaction.
- Memory flush : le prompt de résumé demande les faits durables sur l'utilisateur, au format ligne `MEMOIRE: <fait>` ; chaque fait est sauvé via `memory_store.save(...)` (la dédup sémantique 16a rend ça idempotent). Sans `memory_store`, pas de flush (rien ne bloque).
- Estimation de tokens = `caractères // 4` (heuristique standard, pas d'appel API). Le coût du résumé est compté dans `total_cost_cents`.
- Pas de dépendance nouvelle.

## Changements prévus

### Nouveau module `backend/src/investia/agent/compaction.py`
- `estimate_tokens(messages) -> int` : somme des `len(content) // 4` (+ tool_calls sérialisés).
- `COMPACTION_PROMPT` : prompt de résumé (concis, sections du run, faits durables en lignes `MEMOIRE:`).
- `async def compact_messages(messages, *, llm, model_key, max_tokens, keep_last_turns) -> tuple[list[dict], dict]` : pure côté structure — garde `[system, user(question)]` + les `keep_last_turns` derniers blocs de tour (assistant + tool results), résume le milieu via un appel `llm.chat` (sans outils, temperature 0), insère le résumé marqué untrusted, retourne les nouveaux messages + meta (`dropped_messages`, `summary`, `memoires` listées).
- `parse_memoires(summary_text) -> list[str]` : extrait les lignes `MEMOIRE:`.

### `backend/src/investia/agent/loop.py`
- `_run_once` gagne `context_max_tokens: int | None = None`, `keep_last_turns: int = 4`, `memory_store=None`.
- Au début de chaque tour, avant `llm.chat` : si `context_max_tokens` et `estimate_tokens(messages) > context_max_tokens` → `compact_messages(...)`, remplace `messages`, sauve les `MEMOIRE:` dans `memory_store` (erreurs avalées), émet `compaction` (SSE) + `log_step(run_id, turn, "compaction", {...})`, coût du résumé ajouté à `total_cost`.
- `run_agent` relaie les 3 nouveaux params (rétrocompatible, défauts sûrs).
- `AgentResult` gagne `compactions: int = 0`.

### `backend/src/investia/config.py` + `main.py`
- `context_max_tokens: int | None = 100_000` (env `CONTEXT_MAX_TOKENS`, `0` = désactivé) ; `keep_last_turns: int = 4` (env `COMPACTION_KEEP_LAST_TURNS`).
- `main.py` passe ces réglages + le `memory_store` à `run_agent` sur `/agent/run`.

### AG-UI (15c)
- `"compaction"` ajouté à `CUSTOM_KINDS` dans `agent/agui.py` (CustomEvent nommé).

## Critères d'acceptation

- [ ] `cd backend && uv run pytest tests/test_compaction.py -q` passe (TDD) :
  - `estimate_tokens` (heuristique chars/4) ; `compact_messages` garde system+question+dernier tours, insère le résumé marqué « NON FIABLE », ordre conservé, `parse_memoires` extrait les lignes `MEMOIRE:` ;
  - `run_agent` avec `context_max_tokens` petit (FakeLlm scripté) : event `compaction` émis, le 2e appel LLM reçoit une liste de messages plus courte contenant le résumé untrusted, les faits `MEMOIRE:` sont sauvés dans le fake memory store, `AgentResult.compactions == 1`, status ok ;
  - sans compaction (seuil haut) : aucun event `compaction`, `compactions == 0`, messages envoyés au LLM identiques à aujourd'hui.
- [ ] `uv run pytest -q -m "not integration"` passe en entier ; ruff/ty/format propres.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/compaction.py` | nouveau : `estimate_tokens`, `compact_messages`, `parse_memoires`, `COMPACTION_PROMPT` |
| `backend/src/investia/agent/loop.py` | params `context_max_tokens`/`keep_last_turns`/`memory_store`, hook de compaction par tour, `AgentResult.compactions` |
| `backend/src/investia/agent/agui.py` | `"compaction"` dans `CUSTOM_KINDS` |
| `backend/src/investia/config.py`, `main.py` | env `CONTEXT_MAX_TOKENS` / `COMPACTION_KEEP_LAST_TURNS`, câblage `/agent/run` |
| `backend/tests/test_compaction.py` | tests TDD |
| `docs/STATUS.md` | étape 16c |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_compaction.py tests/test_agent_loop.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/agent tests/test_compaction.py && uv run ty check src/investia/agent
```

## Hors périmètre

- Compaction « sémantique » (garder les messages les plus pertinents plutôt que les plus récents) — sliding window simple d'abord.
- Connexion automatique à la mémoire longue dans le system prompt (le `recall_memory` existe déjà, l'agent l'appelle lui-même).
- Dashboard : l'event `compaction` apparaît en CustomEvent AG-UI / event SSE brut, pas d'UI dédiée.
- Multi-session (mémoire de conversation entre plusieurs runs) : hors sujet ici.
