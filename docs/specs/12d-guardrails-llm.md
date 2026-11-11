# Spec — 12d : Guardrails LLM en renfort (décision + logprobs)

*Écrite le : 08/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 08/11/2026 (elephant-1 + variante logprobs dans la même brique)*

## Objectif

Ajouter deux garde-fous **LLM** en renfort des garde-fous en code, qui jugent si la réponse finale est « sûre / non trompeuse » (au-delà des phrases interdites en dur) :

1. **`safety_llm`** — modèle de décision elephant-1 (`DecisionClient.decide`, D44). Bloque si proba `unsafe` ≥ 0,7 **et** confiance ≥ 0,6.
2. **`safety_logprobs`** — variante LLM-as-Jev : un LLM chat répond Oui/Non à la même question avec `logprobs=True`, on lit la probabilité du premier token (softmax sur les top_logprobs). Bloque si proba « Non » ≥ 0,7.

Les deux sont tracés (event/step `guardrail`) et notés (`safety_llm_ok`, `safety_logprobs_ok`).

## Pourquoi

Le code vérifie des faits (chiffres sourcés, format, phrases interdites). Il ne sait pas juger qu'une formulation est trompeuse sans phrase interdite (« ça va monter », « opportunité »). Un modèle de décision calibré (quasi gratuit) ou les logprobs d'un LLM chat comblent ce trou — **en renfort, jamais à la place** : un « safe » du LLM ne débloque jamais un échec du code. Les deux variantes sont comparées par les evals.

## Contraintes

- Zéro dépendance nouvelle (`DecisionClient` et `LlmClient` existent).
- Rétrocompatible : `run_agent(..., decision_client=None, logprobs_guardrail=False)` — rien n'est exécuté par défaut, comportement inchangé.
- Les checks LLM s'ajoutent aux checks en code, dans le même mécanisme `failed` (correction puis blocage). Ils ne remplacent aucun check existant.
- Dégradé propre : client de décision en erreur → ok=True « indisponible » ; logprobs absents de la réponse → ok=True « logprobs indisponibles ». Jamais de crash.
- Seuils en constantes nommées : `UNSAFE_BLOCK_THRESHOLD = 0.7`, `MIN_CONFIDENCE = 0.6` (elephant), `NON_BLOCK_THRESHOLD = 0.7` (logprobs).
- `LlmChat.chat` gagne `logprobs: bool = False` ; `LlmResponse` gagne `first_token_logprobs: dict[str, float] | None` (probas normalisées du 1er token).
- Coûts tracés dans les steps guardrail.
- Hors périmètre : escalade vers un gros LLM si confiance basse, guardrails sur les entrées (injection côté outils), framework externe (NeMo Guardrails).

## Critères d'acceptation

- [ ] `uv run pytest tests/test_guardrails_llm.py -q` passe (tests écrits avant, TDD).
- [ ] `check_safety_llm` : unsafe 0,9/conf 0,95 → bloqué ; unsafe 0,9/conf 0,3 → passe (confiance basse) ; safe 0,95 → passe ; `decide` qui lève → ok=True « indisponible ».
- [ ] `check_safety_logprobs` : logprobs {"Non": 0,95, "Oui": 0,05} → bloqué ; {"Oui": 0,9} → passe ; `first_token_logprobs` absent → ok=True « indisponible ».
- [ ] `LlmClient.chat(logprobs=True)` : payload contient `logprobs: true` ; réponse parsée en `first_token_logprobs` normalisées (softmax).
- [ ] Boucle : avec `decision_client` et/ou `logprobs_guardrail=True`, les checks `safety_llm` / `safety_logprobs` apparaissent dans `AgentResult.guardrails`, events `guardrail` et steps base ; sans rien → absents (rétrocompat).
- [ ] Métriques `safety_llm_ok` et `safety_logprobs_ok` : 1.0 si safe ou non exécuté, 0.0 si bloqué.
- [ ] 3 nouveaux cas dans `evals/cases.yaml` : `safety-ok` (elephant safe), `safety-unsafe` (elephant unsafe → blocked, `safety_llm_ok=0.0`), `logprobs-unsafe` (`mock_logprobs` Non à 0,95 → blocked, `safety_logprobs_ok=0.0`).
- [ ] `uv run python -m investia.evals` (mock) affiche les deux métriques.
- [ ] `uv run ruff check .`, `uv run ty check`, `uv run pytest -q -m "not integration"` verts ; dashboard 110 tests verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/guardrails/llm_check.py` | création : `check_safety_llm` + `check_safety_logprobs` (seuils en constantes) |
| `backend/src/investia/guardrails/__init__.py` | exports |
| `backend/src/investia/llm/client.py` | `chat(..., logprobs=False)` + `LlmResponse.first_token_logprobs` (parse top_logprobs, softmax) |
| `backend/src/investia/agent/loop.py` | `LlmChat.chat` gagne `logprobs` ; paramètres `decision_client` / `logprobs_guardrail` (wrapper + `_run_once`) ; checks ajoutés après `run_all_checks` |
| `backend/src/investia/evals/metrics.py` | + `safety_llm_ok`, `safety_logprobs_ok` |
| `backend/src/investia/evals/runner.py` | `EvalCase.mock_decision` / `mock_logprobs` + `FakeDecisionClient` ; MockLlm rend la réponse logprobs quand `logprobs=True` |
| `evals/cases.yaml` | + 3 cas (`safety-ok`, `safety-unsafe`, `logprobs-unsafe`) |
| `backend/tests/test_guardrails_llm.py` | tests TDD |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_guardrails_llm.py -q
uv run pytest -q -m "not integration"
uv run ruff check . && uv run ty check
uv run python -m investia.evals
```

## Hors périmètre

Escalade vers un gros LLM si confiance basse, guardrails sur les entrées (injection côté outils), framework externe (NeMo Guardrails). Aucun changement des checks en code existants.
