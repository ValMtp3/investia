# Spec — 17c : fail-closed du sandbox `run_python` + pré-vérification du binaire d'isolation

*Écrite le : 14/11/2026 | Étape roadmap : 17 | Statut : terminée le 14/11/2026 (576 tests non-integration passed / 1 skip, ruff/ty/format propres)*

## Objectif

Si aucun binaire d'isolation OS n'est disponible (ni `nsjail` sur Linux, ni `sandbox-exec` sur macOS), `run_python` doit **refuser d'exécuter** le code au lieu de retomber silencieusement sur un simple sous-processus. Et avant chaque exécution, on vérifie que le binaire requis est bien présent et exécutable (pré-vérification = watchdog de vivacité).

## Pourquoi

Veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §4.3) : CrewAI a eu un cluster de CVE RCE 2026 (CERT/CC VU#221883, CVE-2026-2275/2287/37008) précisément à cause d'un **fallback silencieux vers un sandbox faible quand Docker tombait**. Codex applique l'inverse : si la policy de sandbox ne peut pas être appliquée, il refuse d'exécuter. Aujourd'hui `detect_os_backend()` retourne `"subprocess"` sans binaire → le code tourne avec seulement les patches in-process (socket/subprocess bloqués en Python, mais contournables). C'est exactement la faille.

## Contraintes

- **Fail-closed par défaut** : `INVESTIA_SANDBOX_FAIL_CLOSED` défaut `1`. Si le backend détecté est `subprocess` (pas de binaire OS) → `run_code` lève `SandboxUnavailableError`, le tool `run_python` la traduit en `ToolError` claire. Aucun code exécuté.
- **Opt-out explicite pour le dev local** : `INVESTIA_SANDBOX_FAIL_CLOSED=0` restaure l'ancien comportement (subprocess seul), documenté dans `.env.example`.
- **Pré-vérification avant chaque run** : si le backend choisi est `nsjail` ou `seatbelt`, vérifier `shutil.which(binaire)` + `os.access(..., X_OK)` juste avant le spawn ; binaire disparu entre-temps → `SandboxUnavailableError` (jamais de spawn nu). Si `INVESTIA_SANDBOX_BACKEND` force `nsjail`/`seatbelt` mais que le binaire manque → erreur immédiate (aujourd'hui : `FileNotFoundError` au spawn).
- Zéro régression quand un vrai backend est présent : comportement identique (mêmes rlimits, même profil Seatbelt, champ `backend` dans le résultat). `INVESTIA_SANDBOX_BACKEND=subprocess` explicite reste autorisé (choix délibéré, ex. CI) — mais loggé en warning.
- Tests sans spawner de vrai process sandboxé : monkeypatch de `shutil.which`/`platform.system`/env.

## Changements prévus

### `backend/src/investia/tools/python_sandbox.py`
- `class SandboxUnavailableError(Exception)`.
- `fail_closed_enabled() -> bool` : lit `INVESTIA_SANDBOX_FAIL_CLOSED` (défaut true ; `"0"/"false"/"no"` = off).
- `check_backend_available(backend: str) -> None` : lève `SandboxUnavailableError` si backend ∈ {nsjail, seatbelt} et binaire absent/non exécutable ; si backend == "subprocess" et fail_closed → lève aussi.
- `SubprocessPythonSandbox.run_code` : après `detect_os_backend()`, appeler `check_backend_available(backend)` ; le `os_wrap_command` garde son comportement pour les vrais backends. Le résultat garde `"backend"`.
- `RunPythonTool.run` : `SandboxUnavailableError` → `ToolError(self.name, "sandbox OS indisponible … (fail-closed)")`.

### `backend/src/investia/config.py` + `.env.example`
- `sandbox_fail_closed: bool = True` (env `SANDBOX_FAIL_CLOSED`) — lu par `fail_closed_enabled()` via env directement (le module sandbox lit l'env, comme `BACKEND_ENV` aujourd'hui ; pas besoin de le passer par Settings pour rester testable, mais `.env.example` le documente).

## Critères d'acceptation

- [ ] `cd backend && uv run pytest tests/test_sandbox_fail_closed.py -q` passe (TDD) : auto sans binaire + fail-closed on → `SandboxUnavailableError` et aucun process spawné ; fail-closed off → exécution subprocess (comportement ancien) ; backend forcé `nsjail` sans binaire → erreur immédiate ; backend `nsjail` avec binaire mocké → `check_backend_available` passe ; `run_python` traduit en `ToolError`.
- [ ] `uv run pytest -q -m "not integration"` passe en entier (les tests sandbox existants continuent de passer — ils forcent déjà un backend ou mockent).
- [ ] ruff/ty/format propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/python_sandbox.py` | `SandboxUnavailableError`, `fail_closed_enabled()`, `check_backend_available()`, hook dans `run_code`, traduction dans `RunPythonTool` |
| `backend/tests/test_sandbox_fail_closed.py` | tests TDD |
| `.env.example` | `SANDBOX_FAIL_CLOSED` documenté |
| `docs/STATUS.md` | étape 17c |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_sandbox_fail_closed.py tests/test_tools_python_sandbox.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/tools/python_sandbox.py tests/test_sandbox_fail_closed.py && uv run ty check src/investia/tools
```

## Hors périmètre

- Watchdog temporel en arrière-plan (vérification périodique hors run) — la pré-vérification par run suffit ; un vrai watchdog continu serait un process dédié.
- Migration vers gVisor/Firecracker (veille Go) — piste notée, chantier séparé.
- Changement du profil Seatbelt / des rlimits nsjail.


Post-revue (14/11) : `INVESTIA_SANDBOX_BACKEND=subprocess` explicite autorisé + warning (comme prévu par la spec) ; opt-out `FAIL_CLOSED=0` en fixture autouse des tests sandbox (CI Linux sans nsjail).
