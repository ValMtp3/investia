# Spec 22a — dataset d'evals depuis les traces du VPS + batch live

> Chantier 22 — exploiter les vraies traces de prod (export 14b) pour mesurer
> le harness (et le routeur appris 12h/18a) sur des questions réelles, en
> batch live maîtrisé.

## Contexte

- 14b : `python -m investia.evals.export_traces` → JSONL read-only + sha256
  (champs : id, question, answer, model, status, turns, cost, step_kinds).
- `python -m investia.evals` lance les evals **en mock uniquement**
  (`__main__.py` force `mode="mock"` + fakes).
- `run_evals(..., mode="live")` existe dans le runner mais n'est pas câblé au CLI.
- Garde-fous budget déjà en place (17f) : `LLM_BUDGET_CENTS_PER_CALL` +
  `max_budget` LiteLLM — un batch live reste plafonné.

## Objectif

1. **Enrichir l'export** : chaque ligne JSONL gagne `tools_used` (noms des
   outils appelés, depuis les steps `tool_call`) — sert à `expected_tool`.
2. **Nouveau CLI `build_dataset`** : JSONL de traces → `cases-live.yaml`
   (cas compatibles `EvalCase`), déterministe (seed), filtré (status=ok,
   question+answer non vides), dédupliqué par question normalisée.
3. **Mode `--live` sur `python -m investia.evals`** : vrais LLM/market via
   `build_llm_client`/`build_market_service`, `--cases` + `--limit` garde-fou
   (défaut 20), coût estimé imprimé avant/après.
4. **Procédure VPS documentée** (commandes exactes en docker compose exec).

## Contrat détaillé

### 1. `export_traces.py` — champ `tools_used`

- Depuis les steps du détail (`get_run`), extraire
  `tools_used = [s.payload["name"] for s in steps if s.kind == "tool_call" and name]`
  (dédupliqué, ordre d'appel).
- Rétrocompatible : champ ajouté, rien de retiré. Test : run avec 2 tool_calls
  → tools_used == ["get_quote", "get_history"].

### 2. `build_dataset.py` (nouveau, CLI `python -m investia.evals.build_dataset`)

```
uv run python -m investia.evals.build_dataset \
  --in evals/generated/traces_dataset.jsonl \
  --out evals/generated/cases-live.yaml \
  --limit 50 --seed 42 [--status ok]
```

- Filtre : `status == "ok"` (ou `--status`), `question` non vide, `answer` non vide.
- Dédup : question normalisée (minuscules, espaces collapsés) — garde la trace
  la plus récente.
- Échantillonnage déterministe : `random.Random(seed).sample(...)` sur la
  liste triée par created_at desc, puis tronqué à `--limit`.
- Sortie YAML (même schéma que `cases.yaml`) :
  ```yaml
  cases:
    - id: trace-<id8>
      question: "…"
      expected_tool: get_quote        # premier tools_used, sinon absent
      mock_final: "…"                 # réponse de référence (non rejouée en live)
  ```
- `load_cases(out)` doit relire le fichier (test).
- Le fichier généré est gitignoré (`evals/generated/` déjà ignoré en 14b).

### 3. `__main__.py` — mode `--live`

- `uv run python -m investia.evals --live --cases evals/generated/cases-live.yaml --limit 20`
- `--live` : construit `build_llm_client(settings)` + `build_market_service(settings)`
  (vrais services), appelle `run_evals(cases[:limit], eval_store=store, mode="live")`
  **sans fakes** (web_searcher/pdf_reader/sandbox réels si clés présentes, sinon
  build_tools conditionnel comme en prod).
- Garde-fou : `--limit` défaut 20, max 100 (argparse `type=int` + check) ;
  imprime « batch live : N cas, plafond budget actif (17f) » avant de lancer.
- Mock reste le défaut (zéro régression).

### 4. Procédure VPS (dans STATUS.md à la livraison)

```bash
docker compose exec backend uv run python -m investia.evals.export_traces --limit 200
docker compose exec backend uv run python -m investia.evals.build_dataset \
  --in evals/generated/traces_dataset.jsonl --out evals/generated/cases-live.yaml --limit 30
docker compose exec backend uv run python -m investia.evals --live \
  --cases evals/generated/cases-live.yaml --limit 30
```

## Tests (TDD)

- `test_export_traces.py` (existe ? sinon nouveau) : `tools_used` extrait et dédupliqué.
- `test_build_dataset.py` (nouveau) :
  1. filtre status/question/answer vides ;
  2. dédup par question normalisée (garde la plus récente) ;
  3. seed déterministe : deux appels → même YAML byte-identique ;
  4. `--limit` tronque ; `load_cases` relit le fichier généré ;
  5. `expected_tool` = premier tools_used.
- `__main__` : test léger — parser accepte `--live/--limit`, et `--limit > 100`
  est refusé (SystemExit/argparse error).

## Fichiers touchés

- `backend/src/investia/evals/export_traces.py` (+ `tools_used`)
- `backend/src/investia/evals/build_dataset.py` (nouveau)
- `backend/src/investia/evals/__main__.py` (`--live`, `--limit`)
- `backend/tests/test_export_traces.py`, `backend/tests/test_build_dataset.py`, `test_evals_cli.py` (léger)
- `docs/STATUS.md`, `docs/09-decisions.md` (D93)

## Critères d'acceptation

- Suite non-integration verte, ruff/format/ty propres.
- `build_dataset` produit un YAML relisable par `load_cases`.
- `--live` existe mais le mock reste le défaut ; plafond budget 17f actif.
- ⚠️ Le batch live réel se lance **sur le VPS par le propriétaire** (clés
  réelles) — pas en CI, pas en local ici.

## Hors périmètre

- Scoring LLM-juge (deepeval) sur le dataset live — 14a existe déjà en mock.
- A/B automatique routeur learned vs fixe — lecture manuelle des métriques
  `routeur_choix`/`routeur_agent` du run live dans `/traces`.
- Écriture en base depuis le dataset (read-only, comme 14b).
