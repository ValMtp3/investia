# Spec — 13c : couche OS sous le sandbox run_python + pre-check statique

*Écrite le : 14/11/2026 | Étape roadmap : 13 (sécurité de la boucle) | Statut : terminée le 14/11/2026*

## Objectif

Le sandbox actuel (sous-processus + `resource` + patch `socket`) est une isolation au niveau *processus Python* : il laisse passer ctypes/libc, `io_uring`, l'exfiltration DNS, les fork bombs (RLIMIT_NPROC est par-UID), `/proc` du parent. Cette spec ajoute une **couche OS** (nsjail sur Linux, Seatbelt `sandbox-exec` sur macOS) autour du même sous-processus, plus un **pre-check statique** stdlib du code avant exécution.

## Pourquoi

Veille OSS 14/11/2026 (`docs/veille-oss-2026-11-14.md` brique 1) : en 2026, des agents compromis contournent les patches Python (ctypes vers libc, exfil DNS — incidents AWS AgentCore jan 2026, OpenAI sept 2026). La combinaison bwrap/nsjail + seccomp + netns est celle des CLI de code (Anthropic `sandbox-runtime`, opencode). Zéro dépendance Python ajoutée : ce sont des binaires système.

## Contraintes

- Zéro dépendance Python au runtime. Backends : `nsjail` (Linux, namespaces + rlimits par process) ou `sandbox-exec` (macOS, profil Seatbelt généré à la volée avec le tmpdir en écriture seule) ; sinon repli sur le sous-processus actuel. Sélection : `INVESTIA_SANDBOX_BACKEND=auto|nsjail|seatbelt|subprocess` (défaut `auto` : nsjail si dispo sur Linux, seatbelt si dispo sur macOS, sinon subprocess). Le backend utilisé est retourné dans le résultat (`"backend": "nsjail"|"seatbelt"|"subprocess"`).
- `static_precheck(code)` en AST stdlib (module `ast`, zéro dep) : bloque les imports dangereux (`socket`, `subprocess`, `ctypes`, `multiprocessing`, `os.system`/`popen`/`exec*`/`spawn*`) et les appels `eval`/`exec`/`compile`/`__import__`. Résultat non vide → le code **n'est pas exécuté**, le résultat contient `"precheck": [...]` et `exit_code = -1`.
- Zéro régression : sans binaire OS disponible, comportement strictement identique à aujourd'hui (les tests existants du sandbox passent inchangés). Bandit reste un outil CI/dev (déjà validé en dev), pas un import runtime.
- Le preamble Python (rlimit + patch socket) reste actif en dessous — défense en profondeur.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_sandbox_os.py -q` passe : precheck bloque `import ctypes`, `eval(...)`, `exec(...)`, `__import__(...)`, `import socket`, `os.system(...)` et laisse passer `import math` / calculs purs ; détection de backend (env + `shutil.which` mockés) ; `_os_wrap` produit une commande `nsjail --mode once ... -- python -I -c ...` (Linux), `sandbox-exec -f <profil> -- python ...` (macOS), ou la commande inchangée (repli).
- [ ] Le code bloqué par le precheck n'est jamais exécuté (test avec un code qui écrirait un fichier marqueur : le fichier n'existe pas, `exit_code == -1`).
- [ ] `uv run pytest tests/test_tools_python_sandbox.py -q` passe sans modification (rétrocompat macOS : seatbelt si dispo, profil suffisant pour le preamble ; sinon repli).
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty/format propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/python_sandbox.py` | `static_precheck`, `detect_os_backend`, `_os_wrap`, champ `backend` dans le résultat ; precheck appelé dans `run_code` |
| `backend/tests/test_sandbox_os.py` | tests TDD |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_sandbox_os.py tests/test_tools_python_sandbox.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/tools/python_sandbox.py tests/test_sandbox_os.py && uv run ty check src/investia/tools/python_sandbox.py
```

## Hors périmètre

MicroVM tier 2 (E2B self-host / microsandbox) pour code « dangereux » derrière HITL — piste notée dans la veille, chantier ultérieur. Renforcement du pre-check par Bandit/Semgrep en CI (déjà validé en dev, pas au runtime). Modifications du preamble rlimit. 13d (hash HITL).
