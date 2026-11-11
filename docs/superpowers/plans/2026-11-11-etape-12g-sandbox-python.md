# Plan d'implémentation — Étape 12g : sandbox Python (outil `run_python`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un outil `run_python(code)` qui exécute du code Python généré par l'agent dans un sous-process isolé (tempdir, limites `resource`, réseau bloqué best-effort, env sans secrets), exposé seulement si `python_sandbox` est fourni à `build_tools`, avec 1 cas d'evals mock.

**Architecture:** `tools/python_sandbox.py` — protocol `PythonSandbox` (`run_code(code) -> dict`), `SubprocessPythonSandbox` (stdlib uniquement : `asyncio.create_subprocess_exec(sys.executable, "-I", "-c", preamble+code, cwd=tempdir, env=whitelist, start_new_session=True)` ; limites via `resource.setrlimit` **dans le preamble** (pas de `preexec_fn`, déconseillé en async) ; timeout via `asyncio.wait_for` + `os.killpg(SIGKILL)` ; blocage réseau par patch de `socket.socket`/`socket.create_connection` dans le preamble), `RunPythonTool` (BaseTool, name `run_python`). Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, stdlib (`asyncio`, `subprocess`, `resource` Unix, `tempfile`, `signal`, `os`, `sys`), Pydantic, pytest. Les tests exécutent de vrais sous-process Python locaux (rapides), zéro réseau.

**Spec:** `docs/specs/12g-sandbox-python.md` (validée le 11/11/2026)

## Global Constraints

- Zéro librairie ajoutée. `resource` = Unix only (macOS/Linux) — documenté, pas de support Windows.
- Limites par run : timeout 10 s, CPU 10 s, RAM 512 Mo, ≤ 64 fichiers ouverts, ≤ 10 Mo/fichier écrit, code ≤ 10 000 car., sortie tronquée 20 000 car. Toutes injectables au constructeur (tests rapides).
- Env du fils = whitelist (`PATH`, `LANG`, `HOME`/`TMPDIR` = tempdir) : aucune clé API transmise. `python -I` ignore PYTHONPATH/user-site.
- Rétrocompatible : `build_tools` sans `python_sandbox` → pas d'outil `run_python`, tests existants verts.
- Timeout → `ToolError` « timeout » ; exit_code != 0 = résultat normal (stderr explique), pas une ToolError.
- TDD strict par tâche. Validation : `cd backend && uv run pytest -q -m "not integration"`, `ruff check` + `ty check` sur les fichiers touchés, evals mock, dashboard 110 tests.

## Review Focus

- Aucune clé/secret atteignable depuis le process fils (env whitelist, test explicite).
- Le timeout tue bien tout le groupe de processus (fork bomb contenue : `RLIMIT_NPROC`? non — `start_new_session` + `killpg` + limite CPU).
- Le preamble (limites + blocage socket) ne peut pas être contourné par le code utilisateur (il tourne avant, et `python -I -c` ne lit pas de fichier utilisateur avant).
- Revue sécurité `security-review` obligatoire avant push (exécution de code).

---

### Task 1: `tools/python_sandbox.py` — tests TDD (vrais sous-process locaux)

**Files:**
- Create: `backend/src/investia/tools/python_sandbox.py`
- Create: `backend/tests/test_tools_python_sandbox.py`

**Interfaces:**
- Produces: `PythonSandbox` protocol (`async run_code(code: str) -> dict`), `SubprocessPythonSandbox(timeout=10.0, cpu_seconds=10, memory_bytes=512*1024**2, max_open_files=64, max_file_bytes=10*1024**2, max_code_chars=10_000, max_output_chars=20_000)`, `RunPythonArgs` (code 1..10_000 car.), `RunPythonTool(sandbox)` (name `run_python`).

- [ ] **Step 1: Write failing tests** : `test_print_1plus1_renvoie_stdout_2` ; `test_code_trop_long_validation` (10_001 car. → ValidationError) ; `test_boucle_infinie_timeout` (timeout injecté 1.5 s → ToolError « timeout ») ; `test_env_sans_cle_api` (`os.environ.get("BRAVE_API_KEY")` → None, HOME = tempdir) ; `test_socket_bloque` (`socket.create_connection` → RuntimeError, exit != 0) ; `test_sortie_tronquee` (max_output_chars injecté 100) ; `test_syntax_error_exit_code_2` ; `test_fichier_ecrit_puis_tempdir_supprime` ; `test_tool_run_renvoie_source_timestamp`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : preamble Python (setrlimit CPU/AS/NOFILE/FSIZE + patch socket) + `create_subprocess_exec(sys.executable, "-I", "-c", preamble+code, cwd=tmp, env=SAFE_ENV, start_new_session=True)` ; `asyncio.wait_for` + killpg ; sortie tronquée ; `RunPythonTool.run` → `{"exit_code", "stdout", "stderr", "truncated", "source": "sandbox", "timestamp"}`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(12g): sandbox Python run_python (sous-process isolé, limites resource, réseau bloqué) (TDD)`.

### Task 2: Câblage — `build_tools(..., python_sandbox=None)` + system prompt

**Files:**
- Modify: `backend/src/investia/tools/__init__.py`
- Modify: `backend/src/investia/agent/prompts.py`
- Modify: `backend/tests/test_tools_registry.py`

- [ ] **Step 1: Write failing tests** : `test_build_tools_sans_sandbox_pas_run_python` (rétrocompat) ; `test_build_tools_avec_sandbox_run_python_present` ; system prompt contient « run_python ».
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : `if python_sandbox is not None: tools["run_python"] = RunPythonTool(python_sandbox)` ; phrase dans le system prompt (calculs via run_python, jamais de chiffre calculé de tête).
- [ ] **Step 4: Run** `uv run pytest tests/test_tools_registry.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12g): build_tools câble run_python + prompt système (TDD)`.

### Task 3: Cas d'evals — `FakePythonSandbox` + cas `run-python`

**Files:**
- Modify: `backend/src/investia/evals/runner.py` (+ `FakePythonSandbox`, `run_evals(..., python_sandbox=None)` transmis à `build_tools`)
- Modify: `backend/src/investia/evals/__main__.py` (câble le fake en mode mock)
- Modify: `evals/cases.yaml` (+ cas `run-python`)
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1:** tests : spy `build_tools` reçoit `python_sandbox` ; cas `run-python` (expected_tool `run_python`, mock_final avec un chiffre issu de la sortie mockée, ex. sharpe calculé) → tool_used 1.0.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest tests/test_evals.py -q` → PASS ; evals mock complet (16 cas).
- [ ] **Step 5:** Commit `feat(12g): cas d'evals run-python + FakePythonSandbox (TDD)`.

### Task 4: Revue sécurité + validation globale + docs

- [ ] **Step 1:** Revue `security-review` sur `python_sandbox.py` (exécution de code) + `verification-before-completion` : `cd backend && uv run pytest -q -m "not integration"` vert, `ruff check`/`ty check` sur les fichiers touchés, `test_secrets_hygiene.py` vert, evals mock 16 cas ok.
- [ ] **Step 2:** `cd dashboard && npm run test` → 110 tests verts.
- [ ] **Step 3:** `docs/STATUS.md` (12g terminée), `docs/08-roadmap.md` (12g cochée), `docs/09-decisions.md` (D75 + historique) : subprocess + resource, zéro dépendance, limites, limites connues (pas d'isolation noyau sur macOS, threat model = code LLM).
- [ ] **Step 4:** Commit docs. Demander le push de la branche.
