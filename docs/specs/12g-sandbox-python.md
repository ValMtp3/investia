# Spec — 12g : sandbox Python (outil `run_python`)

*Écrite le : 11/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 11/11/2026 (run_python seul, réseau bloqué best-effort, 10 s / 512 Mo / 20 000 car., flag explicite, zéro dépendance, revue sécurité avant push)*

## Objectif

Un outil `run_python(code)` pour l'agent : exécuter du code Python (calculs, backtests, agrégations) dans un **sous-process isolé**, avec limites de ressources, pour ne plus dépendre des calculs « de tête » du LLM.

## Pourquoi

Un LLM fait des erreurs de calcul. Un outil de calcul fiable complète `web_search` / `read_pdf` (12f). Modèle de menace : le code exécuté est **généré par le LLM de l'agent** (dangereux par maladresse : boucle infinie, `rm`, fork bomb, fuite de secrets), pas par un attaquant externe → un sous-process avec limites (`resource`, tempdir, timeout) est proportionné ; pas besoin de microVM (E2B/nsjail écartés : cloud payant ou Linux-only, voir D75).

## Contraintes

- **Zéro dépendance nouvelle** : `asyncio` + `subprocess` + `resource` (stdlib uniquement).
- Limites par run : timeout 10 s (kill du groupe de processus), CPU 10 s, RAM 512 Mo (`RLIMIT_AS`), ≤ 64 fichiers ouverts, ≤ 10 Mo écrits par fichier, code ≤ 10 000 car., sortie (stdout+stderr) tronquée à 20 000 car.
- Réseau bloqué **best effort** (pas de namespaces sur macOS) : preamble qui fait échouer `socket.socket`, + env réduit à une whitelist (PATH, LANG, HOME=tempdir) — aucune clé API n'est transmise.
- `python -I -c` (mode isolé : ignore PYTHONPATH et site-packages perso), cwd = tempdir supprimé après le run, **pas de shell**.
- `build_tools(..., python_sandbox=None)` : outil présent seulement si le service est fourni (rétrocompatible, comme `web_searcher`/`pdf_reader`). En evals mock : `FakePythonSandbox` déterministe, aucune exécution réelle.
- Revue sécurité obligatoire (`security-review`) avant push de la branche.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_tools_python_sandbox.py -q` passe (vrais sous-process en local, timeout injectable pour ne pas attendre 10 s).
- [ ] `run_python("print(1+1)")` → `exit_code=0`, `stdout="2\n"`.
- [ ] Boucle infinie `while True: pass` → `ToolError` « timeout » (timeout court en test).
- [ ] `os.environ` dans la sandbox ne contient aucune clé API du projet.
- [ ] `import socket; socket.create_connection(...)` échoue (réseau bloqué).
- [ ] `print("x" * 100_000)` → sortie tronquée à 20 000 car.
- [ ] `build_tools` sans sandbox → 4 outils (rétrocompat) ; avec → `run_python` présent.
- [ ] 1 cas d'evals `run-python` (mock, `FakePythonSandbox`) : `tool_used = 1.0`.
- [ ] `uv run pytest -q -m "not integration"`, `ruff check` + `ty check` sur les fichiers touchés, dashboard 110 tests verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/python_sandbox.py` | création : `PythonSandbox` (protocol), `SubprocessPythonSandbox`, `RunPythonTool` |
| `backend/src/investia/tools/__init__.py` | `build_tools(..., python_sandbox=None)` |
| `backend/src/investia/agent/prompts.py` | system prompt cite `run_python` |
| `backend/src/investia/evals/runner.py` + `evals/cases.yaml` | `FakePythonSandbox` + cas `run-python` |
| `backend/tests/test_tools_python_sandbox.py` | création (TDD) |
| `backend/tests/test_tools_registry.py`, `test_evals.py` | ajouts |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_tools_python_sandbox.py -q
uv run pytest -q -m "not integration"
uv run ruff check src/investia/tools/python_sandbox.py && uv run ty check
```

## Hors périmètre

Shell, persistance des fichiers écrits, vraie isolation noyau (nsjail/Firecracker), exécution parallèle de plusieurs codes, installation de packages dans la sandbox, GPU.

## Limites connues (documentées)

Sans namespaces (macOS local), `RLIMIT` limite CPU/RAM/fichiers mais un code *délibérément* malveillant pourrait lire le disque hors tempdir. Accepté : le threat model est le code généré par le LLM, pas un attaquant externe. En prod (VPS Linux), on pourra durcir avec nsjail.
