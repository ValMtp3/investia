# Spec — 1.5 : Client Jev via LiteLLM (/v1/systemone)

*Écrite le : 2026-10-31 | Étape roadmap : 1.5 | Statut : validée*

## Objectif

Appeler le modèle de décision **Jev** (TypeSafe) **via notre gateway LiteLLM** (`POST /v1/systemone`, model `jev`) depuis Python, pour des décisions binaires/catégorielles (routage, garde-fous à l'étape 2). Test de compatibilité Q10/D37 : résolu — LiteLLM ≥ v1.104.2 sert les decision models, notre v1.106.5 expose bien `jev` (`mode: evaluation`) et route vers `typesafe/jev-latest` (testé en local le 31/10 : la requête est validée puis transmise au provider ; seule la clé manque).

## Pourquoi

D16/D37 : Jev pour les décisions (routage, juge) à ~$0.042/M tokens, sortie gratuite. Un seul point d'appel (le gateway) = cost tracking centralisé (D29).

## Contraintes

- `JevClient.decide(state, questions)` → `POST {LITELLM_BASE_URL}/v1/systemone` avec master key, body System One : `{"model": "jev", "state": ..., "questions": {id: {"type": "choice"|"noul"|"score", ...}}}`.
- Format question choice : `{"type": "choice", "instructions": "...", "criteria": {"label": "description ou null"}}` (criteria = map label → description, PAS une string — testé contre le gateway).
- Réponse parsée en `JevAnswer` par question : valeur choisie + `probabilities` + `confidence`. Parsing défensif.
- Erreurs (401, 400, 5xx) → `LlmError` claire. Retry 2× sur 5xx/429 comme le chat.
- Coût suivi via `usage` si présent.
- `jev` déclaré dans `deploy/litellm/config.yaml` (déjà fait) avec `TYPESAFE_API_KEY`.
- Tests : `httpx.MockTransport`, zéro réseau. TDD.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_llm_jev*`).
- [ ] `decide()` mocké (réponse systemone avec probabilities) → `JevAnswer` avec `value`, `probabilities`, `confidence` corrects.
- [ ] Le body envoyé contient bien `model="jev"` et `questions` en dict (vérifié dans le handler mock).
- [ ] 401 (clé manquante côté provider) → `LlmError` avec « typesafe » ou « 401 ».
- [ ] 500 → 2 retries puis `LlmError`.
- [ ] `test_compose.py` incluait déjà les 2 modèles chat ; on y ajoute `jev`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/llm/jev.py` | création : `JevClient`, `JevAnswer` |
| `backend/src/investia/llm/__init__.py` | export + `build_jev_client(settings)` |
| `backend/tests/test_llm_jev.py` | création : tests mockés |
| `backend/tests/test_compose.py` | ajoute `jev` à la liste des modèles litellm |
| `deploy/litellm/config.yaml` | déjà fait (model jev) |

## Comment vérifier

```bash
cd backend && uv run pytest -q
```

## Hors périmètre

Utilisation de Jev dans la boucle/garde-fous (étapes 2+), images/box, long-context. Appel direct TypeSafe (inutile : LiteLLM route).
