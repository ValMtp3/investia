# Spec — 17f : routeur « préserver le cache » + coût/run exposé (tokens cachés) + budget caps gateway

*Écrite le : 14/11/2026 | Étape roadmap : 17 | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026*

## Objectif

Trois briques de la veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §3.5 et §4.7, source opencode v2.2.7 + étude Berkeley sept 2026 « même modèle, coût jusqu'à 5× selon le harness ») :

**A. Règle « préserver le cache »** : un seul modèle par run, jamais de switch en cours de route (le cache prompt côté provider est alors réutilisé à chaque appel). Chez nous le modèle est déjà résolu une fois dans `run_agent` — il manque le **test de non-régression** qui le prouve (routeur qui changerait de réponse à chaque appel) et l'exposé du modèle dans l'event `done`.

**B. Coût/run exposé avec tokens cachés** : parser `usage.prompt_tokens_details.cached_tokens` (champ standard OpenAI/LiteLLM) dans `LlmResponse.cached_tokens` ; tarif caché optionnel `input_cached` dans `models.toml` (DeepSeek cache hit ~0,006 $/M, ~50× moins cher que le peak) appliqué dans `_cost_cents` ; total `cached_tokens` exposé dans `AgentResult` et l'event `done`.

**C. Budget caps au niveau gateway** : plafond `max_budget` + `budget_duration: 30d` dans `deploy/litellm/config.yaml` (general_settings, plafond 20 $/mois = budget projet 10–20 €/mois) ; côté client, `LLM_BUDGET_CENTS_PER_CALL` (défaut 100 c, comportement actuel) câblé via `Settings` dans `build_llm_client`.

## Pourquoi

Le cache prompt est le levier de coût n°1 avec DeepSeek Flash (17b) : changer de modèle en plein run le fait sauter. Exposer les tokens cachés rend ce levier visible dans les traces. Le double plafond (client par appel + gateway par mois) évite qu'un run fouillé ou qu'un mois chargé ne dépasse le budget.

## Contraintes

- Zéro régression : sans champ `cached_tokens` dans la réponse → 0, coût inchangé ; sans `input_cached` dans le TOML → prix plein appliqué à tous les tokens input.
- Le plafond gateway (20 $/30j) est un réglage de déploiement, documenté, pas un secret.
- Pas de dépendance nouvelle.

## Critères d'acceptation (TDD : tests d'abord)

- [x] `LlmClient.chat` parse `prompt_tokens_details.cached_tokens` → `LlmResponse.cached_tokens` (absent → 0) ; `_cost_cents` = cached × prix_caché + (prompt − cached) × prix plein + completion × prix sortie.
- [x] `models.toml` : deepseek-flash `input_cached = 0.006` ; `ModelConfig.price_input_cached_per_m` défaut None (large = None) ; test de non-régression coût sans champ cache.
- [x] Sticky model : `_CachedTokensTracker` wrappe le LLM dans `_run_once` ; test avec routeur « flipping » → `router.calls == 1`, tous les appels du run sur le même modèle ; event `done` (ok/blocked/max_turns/cache) contient `model`, `router_source`, `cached_tokens` ; `AgentResult.cached_tokens` = somme de tous les appels (boucle + plan + réflexion + compaction).
- [x] `Settings.llm_budget_cents_per_call` (env `LLM_BUDGET_CENTS_PER_CALL`, défaut 100.0, gt=0) utilisé par `build_llm_client` (param explicite prioritaire).
- [x] `deploy/litellm/config.yaml` : `max_budget: 20` + `budget_duration: 30d` en general_settings (YAML validé) ; `.env.example` à jour.
- [x] `uv run pytest -q -m "not integration"` : 593 passed / 1 skip ; ruff / format / ty propres.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/llm/client.py` | `cached_tokens` parsé, `_cost_cents` tarif caché |
| `backend/src/investia/llm/models.py` + `models.toml` | `price_input_cached_per_m`, `input_cached = 0.006` deepseek |
| `backend/src/investia/agent/loop.py` | event `done` + `AgentResult.cached_tokens` ; docstring règle cache |
| `backend/src/investia/config.py`, `llm/__init__.py` | `llm_budget_cents_per_call` → `build_llm_client` |
| `backend/tests/test_llm.py`, `tests/test_agent_loop.py` (ou nouveau) | tests TDD |
| `deploy/litellm/config.yaml`, `.env.example`, `docs/STATUS.md` | plafond gateway, doc |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_llm.py tests/test_agent_loop.py -q
cd backend && uv run pytest -q -m "not integration"
# live : un run multi-tours doit montrer cached_tokens > 0 dans l'event done (DeepSeek)
```

## Hors périmètre

- Routage par complexité natif LiteLLM v1.101 côté gateway — on garde notre routeur appris (12h).
- Bifrost (gateway Go) en remplacement de LiteLLM — piste notée, seulement si LiteLLM limite en perf.
- Budget par utilisateur / par clé virtuelle LiteLLM — le plafond global suffit pour le projet.
