# Spec — 1.3 : Client LiteLLM + routeur + budget par exécution

*Écrite le : 2026-10-31 | Étape roadmap : 1.3 | Statut : validée*

## Objectif

Appeler les modèles LLM via le gateway LiteLLM (déjà tournant en local sur `:4000`) depuis Python, avec un routeur petit/gros modèle et un budget maximum bloqué en code.

## Pourquoi

La boucle d'agent (1.4) a besoin d'un client LLM unique et traçable. D29 (LiteLLM gateway multi-provider), D11/D26 (GPT-6 Luna petit, Mistral Large 4 gros), D22 (budget 10-20 €/mois). Les noms de modèles vivent dans un fichier de config, jamais dans le code (doc 03).

## Contraintes

- Client **httpx async** vers `LITELLM_BASE_URL`, master key via env (`LITELLM_MASTER_KEY`), format API OpenAI (`POST /v1/chat/completions`).
- Modèles déclarés dans `backend/src/investia/llm/models.toml` (lu avec `tomllib`, stdlib — zéro dépendance ajoutée) : `small = "gpt-6-luna"`, `large = "mistral-large-4"`.
- **Routeur en dur** au début : règles simples sur la question (ex. longueur/mots-clés « résume » → petit, « analyse » → gros). Le routeur est testé unitairement. Jev arrive à l'étape 1.5.
- **Budget par exécution** : coût max en centimes (config), suivi via `usage` de la réponse ; si dépassé → `LlmError("budget")` claire, arrêt propre.
- Retry limité : 2 tentatives avec backoff sur 429/5xx, timeout 30 s.
- Erreur LiteLLM (401, 404 modèle, 500) → `LlmError` avec le status et le modèle, jamais de réponse fabriquée.
- Coût d'un appel = (prompt_tokens × prix_in + completion_tokens × prix_out) depuis une table de prix dans models.toml (arrondie au centime).
- Tests unitaires via `httpx.MockTransport` (pas d'appel réel) ; test live marqué `@pytest.mark.integration`.
- TDD.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_llm_*`).
- [ ] `client.chat(model="small", messages=[...])` (mocké) → texte de la réponse + `usage` + coût calculé.
- [ ] `router.choose("résume cette actualité") == "small"` ; `router.choose("analyse AAPL en profondeur") == "large"`.
- [ ] Budget dépassé (mock usage énorme) → `LlmError` contenant « budget ».
- [ ] models.toml chargé au démarrage ; changer le nom du modèle dans le toml change celui utilisé (test).
- [ ] HTTP 500 du gateway → `LlmError` après 2 retries, message clair.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/llm/__init__.py` | création : `build_llm_client(settings)` |
| `backend/src/investia/llm/client.py` | création : `LlmClient` (chat, usage, coût, retry, budget) |
| `backend/src/investia/llm/router.py` | création : règles en dur petit/gros |
| `backend/src/investia/llm/models.toml` | création : noms de modèles + prix par M tokens |
| `backend/src/investia/llm/errors.py` | création : `LlmError` |
| `backend/tests/test_llm_*.py` | création : tests mockés + 1 intégration |

## Comment vérifier

```bash
cd backend && uv run pytest -q
# live (clés dans .env) :
OPENAI_API_KEY=... MISTRAL_API_KEY=... LITELLM_API_KEY=... uv run pytest -q -m integration -k llm
```

## Hors périmètre

Boucle d'agent (1.4), Jev (1.5), garde-fous (étape 2), traces OTel (étape 2), cache sémantique LLM (étape 3).
