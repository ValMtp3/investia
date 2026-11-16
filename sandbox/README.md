# sandbox/ — sidecar Go de sandboxing pour run_python (étape 23i, D103)

Binaire **statique** (`CGO_ENABLED=0`) qui reçoit du code Python sur un **unix
socket** et l'exécute dans une sandbox noyau **fail-closed** :

- **Landlock ABI v6** (Linux ≥ 6.12) : lecture/exec sur `/usr /lib /lib64 /bin
  /sbin /etc /dev`, écriture **uniquement** dans le tempdir du run, **aucun
  bind/connect TCP** (deny-all réseau, ABI v6).
- **seccomp-bpf** : bloque mount/ptrace/bpf/modules/namespaces… et `socket()`
  sauf AF_UNIX/AF_NETLINK.
- **rlimits** : CPU, RAM (RLIMIT_AS), NOFILE, FSIZE, NPROC, core=0.
- **timeout** : le parent tue tout le groupe de process.
- Sans Landlock ABI v6 → **503, aucune exécution** (fail-closed, leçon 17c).

Le sidecar ré-exécute lui-même (`__child`) pour appliquer Landlock/seccomp
sur le process fils avant `exec python -I -c`. Zéro dépendance externe hormis
`golang.org/x/sys` (pinné). Le SDK sandlock.io (Rust/cgo) reste une
alternative documentée pour le VPS, non retenue ici pour garder un binaire
statique (choix tranché le 15/11/2026).

## Contrat socket

```
POST /run  {"code": "...", "timeout_s": 10, "max_output_chars": 20000}
→ 200 {"exit_code": 0, "stdout": "...", "stderr": "", "truncated": false, "backend": "sidecar-go"}
→ 503 {"error": "isolation noyau indisponible ..."}   (fail-closed)
```

Socket : `INVESTIA_SANDBOX_SOCK` (défaut `/run/investia/sandbox.sock`).

## Dev

```bash
cd sandbox
go mod tidy
go vet ./...
go test ./...        # run réels seulement si Landlock ABI v6 (CI Linux récent) ; sinon fail-closed testé
INVESTIA_SANDBOX_SOCK=/tmp/sb.sock go run ./cmd/sidecar &
curl --unix-socket /tmp/sb.sock -d '{"code":"print(42)","timeout_s":5}' http://sidecar/run
```

## Docker

```bash
docker build -t investia-sandbox-sidecar .
docker run -v sandbox-sock:/run/investia investia-sandbox-sidecar
```

Le backend Python s'y branche via `INVESTIA_SANDBOX_BACKEND=sidecar` +
`INVESTIA_SANDBOX_SIDECAR_SOCK=/run/investia/sandbox.sock` (voir
`backend/src/investia/tools/python_sandbox.py`, `SidecarSandbox`).
