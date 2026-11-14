# Spec — 12b : Raisonnement structuré, brique 2 — réflexion (auto-critique)

*Écrite le : 08/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 08/11/2026*

## Objectif

En mode `reasoning="reflect"` (combinable : `"plan+reflect"`), chaque **réponse finale candidate** passe d'abord par une passe d'auto-critique : un appel LLM dédié juge la réponse (JSON `{"ok": bool, "problemes": [...]}`) avant les garde-fous. Si la critique trouve des problèmes, la réponse est réinjectée pour correction (mécanisme existant). La passe est tracée (SSE `reflection` + step base) et notée par les métriques `reflexion` et `auto_corrections`.

## Pourquoi

Un agent se trompe parfois sans le savoir (chiffre mal recopié, section oubliée). Lui demander de se relire avant de conclure — comme un auteur relit son texte — réduit les erreurs avant même les garde-fous. Les garde-fous en code restent l'autorité finale : la réflexion ne peut jamais débloquer une réponse que le code bloque.

## Contraintes

- Zéro dépendance nouvelle.
- Rétrocompatible : `"none"` (défaut), `"plan"`, `"reflect"`, `"plan+reflect"` ; toute autre valeur → `ValueError`. Comportement `"none"`/`"plan"` inchangé.
- Parsing de la critique en douceur : JSON illisible → `ok=True` (on laisse les garde-fous décider, la réflexion ne bloque jamais seule).
- Coût de chaque appel de réflexion compté dans `total_cost_cents` (gratuit en mock).
- Pas de changement de modèle ; la réflexion utilise le même `model_key`.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_reasoning_reflect.py -q` passe (tests écrits avant, TDD).
- [ ] Mode `"reflect"` : event SSE `reflection` émis + step `reflection` loggé pour chaque réponse candidate ; `AgentResult.reflections` rempli ; coût compté.
- [ ] Réponse critiquée (`ok=false`) → réinjection + correction, statut final `ok` si la réponse corrigée passe ; `auto_corrections = 1`.
- [ ] Métriques : `reflexion` = 1.0 si au moins une passe a eu lieu, `auto_corrections` = nombre de passes négatives.
- [ ] 2 nouveaux cas dans `evals/cases.yaml` via `mock_responses` (séquence ordonnée) : `reflexion-ok` (passe ok, `reflexion=1.0`, `auto_corrections=0`) et `reflexion-corrige` (passe ko puis réponse corrigée, `auto_corrections=1.0`).
- [ ] `uv run python -m investia.evals` (mock) affiche `reflexion`/`auto_corrections`.
- [ ] Rétrocompat : `"none"`/`"plan"` inchangés, tous les tests existants verts ; `uv run ruff check .`, `uv run ty check`, `uv run pytest -q -m "not integration"` verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/reasoning.py` | + `ReflectionDecision`, `parse_reflection`, `reflect()` |
| `backend/src/investia/agent/prompts.py` | + `REFLECT_PROMPT` |
| `backend/src/investia/agent/loop.py` | modes `"reflect"`/`"plan+reflect"`, appel `reflect()` avant garde-fous, event/step `reflection`, `AgentResult.reflections` |
| `backend/src/investia/evals/metrics.py` | + `reflexion`, `auto_corrections` |
| `backend/src/investia/evals/runner.py` | `EvalCase.mock_responses` (séquence ordonnée) + `reasoning` par cas |
| `evals/cases.yaml` | + 2 cas (`reflexion-ok`, `reflexion-corrige`) |
| `backend/tests/test_reasoning_reflect.py` | tests TDD |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_reasoning_reflect.py -q
uv run pytest -q -m "not integration"
uv run ruff check . && uv run ty check
uv run python -m investia.evals   # métriques reflexion / auto_corrections visibles
```

## Hors périmètre

12c (self-consistency, vote majoritaire sur K runs), guardrails LLM, cache sémantique, routeur appris. La réflexion ne modifie pas les garde-fous en code et ne change pas le prompt système métier.
