# Spec 23i — Sidecar Go de sandboxing (Landlock+seccomp) pour run_python

*Écrite le : 15/11/2026 | Étape veille D94 (item 8 « Écosystème Go ») | Statut : validée le 15/11/2026 (option « Oui, tel quel »)*

## Objectif

Ajouter un **4ᵉ backend d'isolation** pour l'outil `run_python` (12g/17c) : un
**sidecar Go** autonome qui reçoit le code sur un **unix socket**, l'exécute avec
**Landlock + seccomp-bpf fail-closed** (SDK Go sandlock.io, Linux ≥ 6.12) et renvoie
stdout/stderr. Le binaire Go est statique → déployable tel quel sur le VPS.

## Pourquoi

La veille D94 : « la seule brique Go mûre à adopter = un sidecar de sandboxing
(binaire statique spawné par le harness Python, fail-closed) ». Aujourd'hui nos
backends OS dépendent d'un binaire externe (`nsjail`, `sandbox-exec`) installé sur
l'hôte ; un sidecar Go embarque l'isolation noyau dans l'image, sans rien installer
sur le VPS (hors gVisor, procédure documentée séparément).

## Contrat détaillé

### 1. `sandbox/` — projet Go autonome (racine, comme `benchmarks/`)

- `sandbox/go.mod` : module `investia/sandbox`, **Go 1.27**, dep unique pinnée :
  `golang.org/x/sys` (Landlock + seccomp-bpf écrits dans le sidecar, binaire
  statique `CGO_ENABLED=0`). *Choix tranché le 15/11 : le SDK Go sandlock.io est
  un binding cgo (lib Rust à installer sur l'hôte, binaire non statique) → refusé
  au profit de x/sys maison pour garder un binaire statique déployable tel quel.
  Le SDK/CLI sandlock.io (Rust) reste documenté comme alternative VPS en note.*
- `sandbox/cmd/sidecar/main.go` : HTTP stdlib sur unix socket
  (`INVESTIA_SANDBOX_SOCK`, défaut `/run/investia/sandbox.sock`), `POST /run`
  `{code, timeout_s, max_output_chars}` → `200 {exit_code, stdout, stderr, truncated, backend:"sidecar-go"}` ;
  si Landlock/seccomp indisponible → `503` et **aucune exécution** (fail-closed).
- `sandbox/internal/sandboxrun/` : cœur testable `Run(code, opts)` (spawn
  `python -I -c`, rlimits CPU/RAM/NOFILE/FSIZE, timeout + kill process group,
  env whitelist, tempdir nettoyé).
- `sandbox/Dockerfile` : multi-stage `golang:1.27` → binaire statique
  (`CGO_ENABLED=0`), image `investia-sandbox-sidecar`.
- Tests Go `go test ./...` : run hello-world (skip si Landlock ABI < v6),
  fail-closed sur plateforme non supportée, timeout, limites.

### 2. Backend Python — nouveau backend `"sidecar"`

- `VALID_BACKENDS += "sidecar"` ; `detect_os_backend()` : `INVESTIA_SANDBOX_BACKEND=sidecar`
  ou auto si `INVESTIA_SANDBOX_SIDECAR_SOCK` existe.
- `SidecarSandbox(PythonSandbox)` : POST via httpx `AsyncHTTPTransport(uds=sock)` ;
  socket absent/indisponible → `SandboxUnavailableError` (**fail-closed**, jamais de
  repli subprocess silencieux — leçon 17c).
- Le pre-check statique 13c reste appliqué **côté Python avant tout envoi**.
- Câblage : `build_tools(..., python_sandbox=...)` inchangé ; `main.py` choisit
  `SidecarSandbox` si `INVESTIA_SANDBOX_BACKEND=sidecar`, sinon comportement actuel.

### 3. Déploiement

- `deploy/docker-compose.yml` (local) + `deploy/docker-compose.prod.yml` :
  service `sandbox-sidecar` (image buildée depuis `sandbox/Dockerfile`), socket
  partagé via volume `sandbox-sock:/run/investia`, backend avec
  `INVESTIA_SANDBOX_BACKEND=sidecar` + `INVESTIA_SANDBOX_SIDECAR_SOCK`.
- Sur macOS local (pas de Landlock) : `auto` inchangé → Seatbelt. Le sidecar cible
  le VPS Linux. CI (Linux) : `go test ./...` + pytest.

## Critères d'acceptation

- [ ] `cd sandbox && go vet ./... && go test ./...` vert (CI Linux inclus).
- [ ] `cd backend && uv run pytest tests/test_sandbox_sidecar.py -q` vert :
  run ok via fake sidecar (serveur unix socket de test), fail-closed si socket
  absent, precheck appliqué avant envoi, timeout propagé.
- [ ] Suite complète non-integration verte, ruff/format/ty propres, dashboard inchangé.
- [ ] `docker compose` local : sidecar healthy, `run_python` passe par le socket
  (vérifié en local Linux/CI ; sur macOS documenté).
- [ ] Zéro régression : défaut `auto` (nsjail/Seatbelt/subprocess + fail-closed 17c) inchangé.

## Hors périmètre

- gVisor / Agent Substrate sur le VPS : procédure documentée seulement (pas de run ici).
- Remplacer nsjail/Seatbelt : le sidecar s'**ajoute** (4ᵉ backend).
- Le sidecar ne fait pas de réseau avancé (Landlock deny-all réseau suffit).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `sandbox/` (nouveau) | go.mod, cmd/sidecar, internal/sandboxrun, Dockerfile, tests, README |
| `backend/src/investia/tools/python_sandbox.py` | backend `sidecar` + `SidecarSandbox` |
| `backend/src/investia/main.py` (ou factory outils) | câblage env |
| `backend/tests/test_sandbox_sidecar.py` | tests TDD |
| `deploy/docker-compose.yml`, `deploy/docker-compose.prod.yml` | service sidecar + volume |
| `docs/STATUS.md`, `docs/09-decisions.md` (D103) | suivi |

## Comment vérifier

```bash
cd sandbox && go vet ./... && go test ./...
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
cd deploy && docker compose --env-file ../.env up -d sandbox-sidecar
```
