# Spec 23d — Routeur LinUCB/ε-explore + features coût/heure + calibration offline sur le dataset 22a

> Chantier 23d, issu de la veille OSS du 15/11/2026 (`docs/veille-oss-2026-11-15.md`, D94,
> §routeur, pattern OrcaRouter arXiv:2605.30736). Constats à date (vérifiés dans le code) :
> - **12h en place** : `LearnedRouter` (k-NN pgvector pondéré sur `router_feedback`, k=7,
>   fallback règles D44 si < 5 voisins ou écart < 0,1), `DbRouterFeedback`, `run_agent(router=...)`,
>   `AgentResult.router_source` (explicit|learned|rules), feedback `record(question, model,
>   success)` après chaque run, métrique `routeur_choix`, evals `routeur-learned`/`routeur-fallback`.
> - Table `router_feedback` (migration 0008) : `question, model, success, embedding` — **pas de
>   colonne coût**.
> - Prix des modèles déjà parsés : `llm/models.py` (`ModelConfig.price_input_per_m`,
>   `price_output_per_m`, `price_input_cached_per_m` depuis `models.toml`).
> - **Trous restants** (veille) : (1) pas de LinUCB/ε-explore au-dessus du k-NN ; (2) pas de
>   features coût/heure (off-peak DeepSeek −50 % hors 01:00–04:00 & 06:00–10:00 UTC lun–ven) ;
>   (3) pas de calibration du seuil vs budget hors-ligne sur le dataset 22a
>   (RouterArena ICLR 2026, arXiv:2510.00202, comme scorer externe — lecture manuelle).

## Objectif

Ajouter un **routeur LinUCB avec exploration ε** au-dessus du k-NN existant, avec des
**features coût/heure**, persistant, et un **CLI de calibration offline** sur les feedbacks
/le dataset 22a. TDD, zéro régression : le mode par défaut reste `knn` (12h inchangé).

### 1. Cœur LinUCB pur stdlib — `llm/linucb.py` (nouveau, zéro dépendance)

- Vecteur de features `d = 7`, construit par `build_features(question, *, knn_scores, now,
  prices, budget_cents, cost_estimate_cents)` :
  - `f0 = 1.0` (biais)
  - `f1 = score k-NN small` (0.0 si aucun voisin — features issues des voisins 12h)
  - `f2 = score k-NN large`
  - `f3 = min(len(question), 500) / 500` (longueur normalisée)
  - `f4 = prix effectif small / prix catalogue small` (avec remise off-peak, §3)
  - `f5 = prix effectif large / prix catalogue large`
  - `f6 = min(cost_estimé, budget) / budget` (coût prédit de la requête vs budget)
- Classe `LinUCB(d, arms=("small", "large"), alpha=0.5, epsilon=0.05, lam=1.0)` :
  - par bras : `A = λ·I(d×d)`, `b = 0(d)` ;
  - `choose(x, rng)` → avec proba `epsilon` un bras au hasard (source `"explore"`), sinon
    argmax de `x·θ_a + alpha·sqrt(xᵀ·A_a⁻¹·x)` (source `"linucb"`) avec `θ_a = solve(A_a, b_a)`
    et `A_a⁻¹·x = solve(A_a, x)` — **Gauss-Jordan stdlib**, d=7 donc O(d³) négligeable
    (pas besoin de Sherman-Morrison à cette taille) ;
  - `update(arm, x, reward)` : `A += x·xᵀ`, `b += reward·x`, `n += 1` ;
  - **anti-windup** (boucle fermée stable, OrcaRouter) : reward clampé dans [0, 1]
    (§4), `alpha` fixe, `lam = 1`, et si `A` devient singulière (pivot < 1e-12 au solve)
    → reset du bras `A = λ·I, b = 0, n = 0` (bras redevenu froid).
- Sérialisation pure : `to_dict()` / `from_dict()` (listes Python) pour persistance.

### 2. Persistance — migration 0012 + `DbLinUCBStore`

- Migration **0012** : `ALTER TABLE router_feedback ADD COLUMN cost_cents DOUBLE PRECISION NULL`
  (rétrocompatible) + table
  `router_linucb (arm TEXT PRIMARY KEY, a DOUBLE PRECISION[] NOT NULL, b DOUBLE PRECISION[] NOT NULL, n INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())`.
- `DbLinUCBStore` (dans `llm/router_store.py`) : `load() -> dict[arm, LinUCB-state]`,
  `save(arm, state)` (upsert), + `all_feedbacks() -> list[(question, model, success, cost_cents)]`
  sur `router_feedback` (pour la calibration §5). `DbRouterFeedback.record` gagne
  `cost_cents: float | None = None` (écrit la colonne).

### 3. Features coût/heure — `effective_price(model: ModelConfig, now: datetime) -> float`

- Constantes `OFF_PEAK_WINDOWS` (UTC) : remise −50 % hors 01:00–04:00 et 06:00–10:00
  lun–ven pour le modèle small (DeepSeek, cf. veille) — dans `linucb.py`, testable.
- `effective_price` applique la remise sur `price_input_per_m` si `now` est **hors** des
  fenêtres plein tarif (lun–ven 01:00–04:00 et 06:00–10:00 UTC) ; retourne le prix effectif.
  Test : un lundi 02:00 UTC (fenêtre peak) → plein tarif, un lundi 12:00 UTC → −50 %.

### 4. `LinUCBRouter` — même interface que `LearnedRouter`

- `choose(question) -> tuple[model_key, source]` avec source ∈ `"rules" | "linucb" | "explore"` :
  cold start (`n_total < min_feedbacks`, défaut 5) → règles D44 (source `"rules"`) ;
  sinon `LinUCB.choose` sur les features (k-NN via `RouterFeedbackStore.neighbors` pour f1/f2).
- `record(question, model, success, cost_cents=0.0)` : écrit le feedback k-NN (avec coût)
  **et** met à jour le bras LinUCB : `reward = clamp((1.0 if success else 0.0) - cost_weight *
  cost_cents / max(budget_cents, 1), 0.0, 1.0)` ; persiste via `DbLinUCBStore`.
- `run_agent` : `router.record(question, resolved_model, status == "ok", cost_cents=result.total_cost_cents)`
  (rétrocompatible : `LearnedRouter.record` accepte `cost_cents` ignoré en kw).

### 5. Calibration offline — CLI `python -m investia.evals.calibrate_router`

```
uv run python -m investia.evals.calibrate_router \
  --source feedbacks            # ou --cases evals/generated/cases-live.yaml (mock)
  --out evals/generated/router_calibration.json --seed 42
```

- Charge les feedbacks (`DbLinUCBStore.all_feedbacks()`), rejoue la boucle fermée en
  simulation déterministe (`random.Random(seed)`) : pour chaque feedback, `build_features`
  + `LinUCB.choose` + `update` avec le reward §4.
- **Sweep** sur grille : `alpha ∈ {0.1, 0.3, 1.0}`, `epsilon ∈ {0.0, 0.05, 0.1}`,
  `cost_weight ∈ {0.0, 0.1, 0.5}` → pour chaque combinaison : `mean_reward`,
  `success_rate`, `mean_cost_cents`, `total_cost` ; sélection = meilleur `mean_reward`
  sous contrainte `success_rate ≥ 0.8` (seuil `--min-success`, défaut 0.8), ex-aequo →
  coût total le plus faible.
- Sortie : JSON (`{seed, grid, results: [...], best: {alpha, epsilon, cost_weight, ...}}`)
  dans `evals/generated/` (gitignoré) + table imprimée. Le scorer externe RouterArena
  reste une lecture manuelle (hors périmètre code).
- Runtime : les hyperparams lus via env `ROUTER_LINUCB_ALPHA` / `ROUTER_LINUCB_EPSILON` /
  `ROUTER_LINUCB_COST_WEIGHT` (défauts 0.5 / 0.05 / 0.1) dans `config.py`.

### 6. Wiring — `ROUTER_MODE` env

- `config.py` : `router_mode: str = Field(default="knn")` (`"knn" | "linucb"`).
- `main.py` : si `linucb` → construit `LinUCBRouter(DbRouterFeedback + DbLinUCBStore + models config)` ;
  défaut `knn` = comportement 12h **inchangé** (zéro régression).

## Tests (TDD)

- `test_linucb.py` (nouveau) : solve Gauss-Jordan (A·θ=b vérifié), Sherman-Morrison
  (A⁻¹·A = I), choose explore vs ucb (seed fixé), update change θ, clamp reward [0,1],
  reset anti-windup si det ≈ 0, to_dict/from_dict roundtrip, `build_features` (7 dims,
  off-peak : lundi 02:00 UTC → remise, lundi 12:00 → plein tarif), cold start → rules.
- `test_router_linucb.py` : `LinUCBRouter.choose` source rules/linucb/explore, `record`
  met à jour le bras + écrit le feedback avec coût (fake stores).
- `test_calibrate_router.py` : déterminisme (2 runs, seed identique → JSON identique),
  schéma JSON, `best` ∈ grille, contrainte success_rate respectée, `--cases` mock lit
  un YAML `cases-live.yaml` synthétique.
- `test_loop` (suite) : `record` appelé avec `cost_cents` = total du run.
- Intégration pgvector marqués `@pytest.mark.integration` : `DbLinUCBStore` load/save
  roundtrip, `all_feedbacks`, migration 0012 (via `alembic upgrade head` de test_db).

## Fichiers touchés

- `backend/src/investia/llm/linucb.py` (nouveau)
- `backend/src/investia/llm/router.py` (record + cost_cents kw, import LinUCBRouter)
- `backend/src/investia/llm/router_store.py` (DbLinUCBStore, all_feedbacks, cost_cents)
- `backend/src/investia/agent/loop.py` (record avec cost_cents)
- `backend/src/investia/config.py` (router_mode + 3 env hyperparams)
- `backend/src/investia/main.py` (wiring linucb)
- `backend/src/investia/evals/calibrate_router.py` (nouveau CLI)
- `backend/alembic/versions/0012_router_linucb.py`
- tests : `test_linucb.py`, `test_router_linucb.py`, `test_calibrate_router.py`, + suites existantes
- `docs/STATUS.md`, `docs/09-decisions.md` (D99)

## Critères d'acceptation

- Suite non-integration verte, ruff/format/ty propres ; dashboard inchangé.
- `ROUTER_MODE=knn` (défaut) : tous les tests 12h passent sans modification de comportement.
- `ROUTER_MODE=linucb` : `router_source` ∈ {rules, linucb, explore} tracé ; feedbacks avec coût.
- Calibrator déterministe, JSON relisable, `best` dans la grille, contrainte succès respectée.
- ⚠️ Batch live de calibration (vraies traces VPS) = action propriétaire, jamais en CI.

## Hors périmètre

- Cache sémantique namespacé par user (item veille CVE-2026-89032) — chantier séparé.
- RouterArena en scorer automatique — lecture manuelle du JSON de calibration.
- Remplacement du k-NN par LinUCB seul (on garde les deux, switch par env).
