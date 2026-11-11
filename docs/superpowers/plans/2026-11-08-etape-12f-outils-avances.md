# Plan d'implémentation — Étape 12f : outils avancés (web_search + read_pdf)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deux outils lecture seule pour l'agent : `web_search` (Brave Search API) et `read_pdf` (Nutrient DWS API), enregistrés dans `build_tools` seulement si le service est fourni, testés en mock, avec 2 cas d'evals.

**Architecture:** Appels HTTP directs (httpx) dans `tools/web_search.py` et `tools/pdf.py`, pattern `BaseTool` + schéma Pydantic + `ToolError`. Clés optionnelles `BRAVE_API_KEY` / `NUTRIENT_API_KEY` dans config + `.env.example` (sans clé → ToolError « clé manquante »). Contenus tronqués (web 500 car./résultat, PDF 20 000 car.). Zéro librairie ajoutée.

**Tech Stack:** Python 3.12+, httpx (MockTransport en test), Pydantic, pytest. Zéro réseau en test.

**Spec:** `docs/specs/12f-outils-avances.md` (validée le 08/11/2026)

## Global Constraints

- Zéro librairie ajoutée ; clés jamais dans le code (`.env` uniquement, `test_secrets_hygiene.py` veille).
- Rétrocompatible : `build_tools` sans les nouveaux services → 4 outils, tests existants verts.
- Sans clé API → `ToolError` clair, jamais de valeur inventée. Erreurs HTTP (429/500) → ToolError lisible.
- Sorties avec `source` + `timestamp` (règle des outils, doc 03).
- TDD strict par tâche. Validation : `cd backend && uv run pytest -q -m "not integration"`, `uv run ruff check .`, `uv run ty check`, evals mock.

## Review Focus

- Un outil sans clé ne doit jamais renvoyer de contenu fabriqué.
- Les contenus tronqués tiennent dans le contexte du LLM (500 car./résultat web, 20 000 car. PDF).
- `read_pdf` refuse les URL non-PDF (Content-Type ou extension) et les PDF > 20 Mo avant téléchargement.
- Timeout 30 s partout ; erreurs réseau → ToolError.

---

### Task 1: Config + `tools/web_search.py` (Brave) — tests TDD

**Files:**
- Modify: `backend/src/investia/config.py` (+ `brave_api_key: SecretStr | None = None`)
- Modify: `.env.example` (+ `BRAVE_API_KEY=`)
- Create: `backend/src/investia/tools/web_search.py`
- Create: `backend/tests/test_tools_web_search.py`

**Interfaces:**
- Produces: `WebSearcher` protocol (`search(query, limit) -> list[dict]`) + `BraveWebSearcher(api_key, base_url="https://api.search.brave.com/res/v1", http_client=None)` + `WebSearchTool(searcher)` (BaseTool, name `web_search`).

- [ ] **Step 1: Write failing tests** (MockTransport) : `test_sans_cle_tool_error` ; `test_search_renvoie_resultats_source_timestamp` (mock 200 Brave → titre/url/extrait tronqué à 500 car.) ; `test_429_vers_tool_error` ; `test_limite_1_10` (validation Pydantic, limit=0 → erreur) ; `test_tool_run_renvoie_source_timestamp`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : client Brave (`GET /web/search?q=...&count=...`, header `X-Subscription-Token`), parsing `web.results[]` ; `WebSearchTool.run` → `{"query":..., "results": [...], "source": "brave", "timestamp": ...}`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(12f): outil web_search (Brave) + config BRAVE_API_KEY (TDD)`.

### Task 2: `tools/pdf.py` (Nutrient DWS) — tests TDD

**Files:**
- Modify: `backend/src/investia/config.py` (+ `nutrient_api_key: SecretStr | None = None`)
- Modify: `.env.example` (+ `NUTRIENT_API_KEY=`)
- Create: `backend/src/investia/tools/pdf.py`
- Create: `backend/tests/test_tools_pdf.py`

**Interfaces:**
- Produces: `PdfReader` protocol (`extract_text(url, max_pages) -> str`) + `NutrientPdfReader(api_key, http_client=None)` + `ReadPdfTool(reader)` (name `read_pdf`).

- [ ] **Step 1: Write failing tests** : `test_sans_cle_tool_error` ; `test_url_non_pdf_refusee` (Content-Type text/html → ToolError) ; `test_extrait_texte_tronque_20000` (mock Nutrient → texte long tronqué + source/timestamp) ; `test_max_pages_1_20` ; `test_timeout_ou_erreur_vers_tool_error`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : client Nutrient DWS (`POST /api/process` ou endpoint extraction texte — vérifier doc Nutrient, payload `{url}` / fichier), vérif Content-Type/extension `.pdf`, limite 20 Mo, tronque à 20 000 car. ; `ReadPdfTool.run` → `{"url":..., "text": ..., "pages":..., "source": "nutrient", "timestamp": ...}`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(12f): outil read_pdf (Nutrient DWS) + config NUTRIENT_API_KEY (TDD)`.

### Task 3: Câblage — `build_tools(..., web_searcher=None, pdf_reader=None)` + system prompt

**Files:**
- Modify: `backend/src/investia/tools/__init__.py`
- Modify: `backend/src/investia/agent/prompts.py`
- Modify: `backend/tests/test_tools_registry.py` (ou nouveau test)

- [ ] **Step 1: Write failing tests** : `test_build_tools_sans_services_4_outils` (rétrocompat) ; `test_build_tools_avec_services_6_outils` (web_search + read_pdf présents) ; system prompt contient « web_search » et « read_pdf ».
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : dans `build_tools`, si `web_searcher is not None` → `tools["web_search"] = WebSearchTool(web_searcher)` ; idem pdf. System prompt : ajouter la phrase listant les nouveaux outils.
- [ ] **Step 4: Run** `uv run pytest tests/test_tools_registry.py tests/test_tools.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12f): build_tools câble web_search/read_pdf + prompt système (TDD)`.

### Task 4: Cas d'evals — 2 nouveaux cas

**Files:**
- Modify: `evals/cases.yaml`
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1:** test `test_run_evals_nouveaux_outils` : cas `web-search` (expected_tool web_search, mock_tool_call web_search) et `read-pdf` (expected_tool read_pdf) → tool_used 1.0. Note : les outils ne sont enregistrés que si le service est fourni — le test passe un FakeWebSearcher/FakePdfReader à run_evals (étendre run_evals avec `web_searcher`/`pdf_reader` optionnels transmis à build_tools).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement : `run_evals(..., web_searcher=None, pdf_reader=None)` transmis à `build_tools` ; 2 cas YAML. Les mock_final contiennent un chiffre sourcé par la sortie mockée de l'outil (ex. un prix trouvé sur le web).
- [ ] **Step 4:** Run `uv run pytest tests/test_evals.py -q` → PASS ; evals mock complet.
- [ ] **Step 5:** Commit `feat(12f): cas d'evals web-search / read-pdf (TDD)`.

### Task 5: Validation globale + docs

- [ ] **Step 1:** `cd backend && uv run pytest -q -m "not integration"` → vert ; `uv run ruff check .` ; `uv run ty check` ; `uv run pytest tests/test_secrets_hygiene.py -q` (les nouvelles lignes .env.example ne fuient rien).
- [ ] **Step 2:** `cd dashboard && npm run test` → 110 tests verts (aucun changement frontend).
- [ ] **Step 3:** `docs/STATUS.md` (12f terminée), `docs/08-roadmap.md` (12f cochée), `docs/09-decisions.md` (D74 + historique + nouvelles clés listées comme TWELVEDATA/MASSIVE).
- [ ] **Step 4:** Commit docs.
