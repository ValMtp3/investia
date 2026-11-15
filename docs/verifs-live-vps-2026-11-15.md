# Vérifications live VPS — checklist du 15/11/2026

Tout se fait **sur le VPS, par le propriétaire, avec les vraies clés** (`.env` prod).
Rien de ceci ne tourne en CI ni en local. Cocher au fur et à mesure.

## 0. Prérequis

- [ ] `bash ~/investia/deploy/update.sh` à jour (main = `b073a61`, chantier 22a mergé)
- [ ] `alembic upgrade head` OK (head attendu : `0010_agent_feedback`)

## 1. Sécurité — LiteLLM (backdoors 2026, veille 15/11 D94/D95)

- [x] Bump version : image gateway déjà `ghcr.io/berriai/litellm:v1.109.1` (backport sécu #51254) dans `deploy/docker-compose.yml` — verrouillé par test (23a), plus de tag flottant
- [ ] ⚠️ Backdoors 2026 à ne JAMAIS tirer : `1.82.7`/`1.82.8` (TeamPCP, mars) et `1.107.0` (21/10, MAL-2026-2144) — si l'une d'elles a tourné sur le VPS : **rotation de toutes les clés providers**
- [ ] Pin par **digest** + vérification **cosign** (owner, hors CI) : `cosign verify --key cosign.pub ghcr.io/berriai/litellm:v1.109.1` puis `image: ...@sha256:<digest>` dans le compose prod
- [ ] Après `update.sh` : vérifier `GET /health` du gateway + un run chat simple ; `internal_user_viewer` désactivé (GHSA-g5ff-637f-6q2m, lecture `/proc/self/environ` → master key)

## 2. Étape 11 — rôles PostgreSQL applicatifs (D68, one-shot)

- [ ] `INVESTIA_APP_DB_PASSWORD` / `LITELLM_APP_DB_PASSWORD` renseignés dans le `.env` VPS + URLs mises à jour
- [ ] `sh deploy/postgres/apply-app-roles.sh` exécuté une fois
- [ ] Vérifier : `psql` en `investia_app` migre/refuse cross-base comme attendu ; `pg_dump` admin toujours OK

## 3. Étape 17a — schéma exact de `/v1/forecast` (Timestral)

- [ ] Un run avec l'outil `get_forecast` (ex. `Prévision AAPL sur 30 jours, horizon 5 jours`) en prod
- [ ] Comparer la réponse brute (curl `POST https://api.mistral.ai/v1/forecast` avec la clé VPS, modèle `timestral-1-0-209m`) au schéma attendu par `market/forecast.py` (quantiles 0.1/0.5/0.9, horizon) — le parseur est tolérant, confirmer qu'aucun champ utile n'est ignoré
- [ ] Noter tout écart dans `docs/STATUS.md` (⚠️ de l'étape 17a)

## 3b. Étape 23b — guard d'injection ONNX local (optionnel)

- [ ] Télécharger le modèle épinglé en local sur le VPS : `Horizon-Labs/prompt-injection-guard-small` (mmBERT 140M, ONNX, Apache-2.0, maj 09/11/2026 — entraîné sur Nemotron indirect-injection + llmail), fichier `.onnx` + tokenizer dans `/opt/models/prompt-injection-guard-small/`
- [ ] Renseigner `INJECTION_GUARD_MODEL_PATH` dans le `.env` VPS + `update.sh`
- [ ] Vérifier au démarrage d'un run que le scanner est actif (sinon repli regex 13b, zéro crash) ; `onnxruntime`/`transformers` s'installent côté backend si présents (imports lazy, jamais de téléchargement réseau au runtime)

## 4. Étape 17b — gotcha `reasoning_content` (DeepSeek Flash, tier « small »)

- [ ] Lancer **3+ runs consécutifs multi-outils** en prod avec le tier small (questions qui déclenchent `get_quote` + `get_history` + `get_news`)
- [ ] Vérifier : aucune erreur 400 LiteLLM liée à `reasoning_content` dans les logs backend, et le champ thinking n'apparaît pas en clair dans les traces `/traces` (redaction 13a)
- [ ] Note : lancer les evals batch en fenêtre **off-peak DeepSeek** (lun–ven 01:00–04:00 et 06:00–10:00 UTC, −50 %)

## 5. Étape 17h — workflow CVE Alerts en réel

- [ ] `workflow_dispatch` du workflow `cve-alerts.yml` sur main → le run scan bien les lockfiles + images (trivy v0.67.2)
- [ ] Si findings HIGH/CRITICAL : une issue `[CVE] scan du <date>` est créée automatiquement

## 6. Étape 20d — visuel du polish UI en prod

- [ ] Captures des 4 pages (`/marche`, `/portefeuille`, `/agent`, `/traces`) : transitions 150 ms, skeletons, zebrage, AllocationBar animée — la DA « salle de contrôle » (D63) est inchangée

## 7. Étape 21a — panneau « État du run » (AG-UI) en prod

- [ ] Ouvrir `/agent?protocol=agui`, lancer un run : le panneau « État du run » se met à jour en direct (statut, agents, steps)
- [ ] Vérifier aussi le rendu `ui_component` (21b) : un appel `get_history` affiche le graphique `HistoryChart` dans la bulle du chat
- [ ] Mode legacy (`/agent` sans paramètre) inchangé : zéro régression

## 8. Chantier 22a — batch live depuis les vraies traces (D93)

```bash
cd ~/investia/deploy && docker compose exec backend uv run python -m investia.evals.export_traces --limit 200
docker compose exec backend uv run python -m investia.evals.build_dataset \
  --in evals/generated/traces_dataset.jsonl \
  --out evals/generated/cases-live.yaml --limit 30 --seed 42
docker compose exec backend uv run python -m investia.evals --live \
  --cases evals/generated/cases-live.yaml --limit 30
```

- [ ] Export : `tools_used` présent sur chaque ligne du JSONL
- [ ] Dataset : `cases-live.yaml` généré, ~30 cas `trace-<id8>`, déterministe (rejouer avec le même seed = même fichier)
- [ ] Batch live : « batch live : 30 cas, plafond budget actif (17f) » puis métriques par cas ; plafond `--limit` max 100 respecté
- [ ] Lecture des métriques du run live dans `/traces` : `routeur_choix`, `routeur_agent`, `tool_used` — à comparer au run mock de référence
- [ ] Coût total du batch noté (centimes) pour calibrer les prochains batchs
