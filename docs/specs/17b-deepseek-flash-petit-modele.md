# Spec — 17b : DeepSeek V4.1-Flash comme tier « petit modèle » du routeur (via LiteLLM)

*Écrite le : 14/11/2026 | Étape roadmap : 17 | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026 (small = deepseek/deepseek-flash-latest, large inchangé)*

## Objectif

Faire du tier `small` du routeur le modèle **DeepSeek V4.1-Flash-1017** (`deepseek/deepseek-flash-latest` via LiteLLM), à la place de `gpt-6-luna` : ~0,30 $/M en input (cache miss) et 1,20 $/M en output en peak, moitié en off-peak, cache hit ~50× moins cher — et benchmarks 2026 au niveau (SWE-bench ~80 %, LiveCodeBench 93,5, chiffres DeepSeek ⚠️ auto-déclarés).

## Pourquoi

Veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §3) : LiteLLM (notre gateway) route nativement `deepseek/*` avec alias `-latest` qui suit les checkpoints ; le cache serveur DeepSeek rend les prompts système répétés quasi gratuits — idéal pour notre boucle (même system prompt à chaque tour). Le routeur appris (12h) continue de choisir small/large ; seul le modèle derrière `small` change.

## Contraintes

- **Config uniquement** : `backend/src/investia/llm/models.toml` — `small = "deepseek/deepseek-flash-latest"` + prix (input 0.30, output 1.20, prix peak cache-miss, conservateur). `large` inchangé (`mistral-large-4`).
- Zéro régression code : aucun changement Python ; le routeur, le cache sémantique, les evals mock restent identiques (ils mockent le LLM).
- **Gotcha `reasoning_content`** (veille) : en mode thinking, le champ `reasoning_content` doit être renvoyé à l'API, sinon la conversation casse au 2ᵉ–3ᵉ tour d'outils. LiteLLM gère ce champ côté provider deepseek ; on le vérifie dans les evals (cas existant `routeur-fallback`/`routeur-learned` + un test unitaire qui assert juste la config). ⚠️ test live à faire sur le VPS avec une vraie question avant de valider en prod.
- **Gouvernance données** : ban fédéral US du 20/10/2026 (serveurs en Chine) → la redaction PII (13a) reste active en amont de LiteLLM ; on n'envoie que des données de marché/simulation. C'est documenté, pas un blocage pour un projet d'apprentissage avec données fictives.
- Pas de dépendance nouvelle (LiteLLM déjà là, ≥ v1.109.1 épinglé pour la backdoor CVE-2026-33634).

## Critères d'acceptation

- [x] `models.toml` : small = deepseek/deepseek-flash-latest avec prix (clé TOML quotée — les `/` ne sont pas valides en clé nue) ; `uv run pytest tests/test_llm.py tests/test_llm_router_learned.py -q -m "not integration"` passe (asserts existing mis à jour, dont coût 0.042 centime avec les nouveaux prix).
- [x] Nouveau test : `load_models_config().small.name == "deepseek/deepseek-flash-latest"` et prix > 0.
- [x] `uv run pytest -q -m "not integration"` passe en entier : 577 passed / 1 skip (macOS pré-existant) ; ruff/ty/format propres.
- [x] Note opérationnelle dans STATUS.md : lancer les evals batch en fenêtre off-peak DeepSeek (lun–ven 01:00–04:00 et 06:00–10:00 UTC, −50 %).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/llm/models.toml` | small → deepseek/deepseek-flash-latest + prix |
| `backend/tests/test_llm.py` | asserts mis à jour + nouveau test |
| `docs/STATUS.md` | étape 17b + note off-peak |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_llm.py tests/test_llm_router_learned.py -q
cd backend && uv run pytest -q -m "not integration"
# live VPS (une fois) : poser une question simple, vérifier dans les traces que
# le modèle utilisé est deepseek-flash et que la conversation tient sur 3+ tours d'outils
```

## Hors périmètre

- Changer le tier `large`, ajouter un 3ᵉ tier.
- Le routage par complexité natif de LiteLLM v1.101+ (veille) — on garde notre routeur appris maison (12h), qui apprend de nos evals.
- Self-hosting DeepSeek (poids MIT sur HF) — piste notée, pas pour maintenant.
- Le ban US / conformité RGPD : documenté, pas de code.
