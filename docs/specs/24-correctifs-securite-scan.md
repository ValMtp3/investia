# Spec — Correctifs sécurité du scan Sunfire (17 findings medium)

*Écrite le : 20/11/2026 | Étape roadmap : 24 (suite chantier sécurité) | Statut : validée*

## Objectif

Corriger les 17 findings **medium** du scan de sécurité Sunfire (run `20261120-194630-ed1b38`, 0 critical / 0 high / 17 medium / 11 low). Les 11 low restent en l'état (décision propriétaire, ce chantier = medium uniquement).

## Pourquoi

Scan `vibe-security:code-vulnerability-scanning` du 20/11/2026 : le chemin A2A lance des runs LLM sans les garde-fous du chemin principal, l'approbation humaine est liée à un simple run_id (bearer), le résumé de compaction (non fiable) est injecté en rôle `system` et ses lignes `MEMOIRE:` persistées sans filtrage, plusieurs boucles/ressources sont non bornées (DoS), le `request_state` MCP est un hash non salé forgeable par le client, et les exports de traces partent dans un dossier non gitignoré.

## Contraintes

- Zéro régression : comportement par défaut inchangé quand la config est vide (rétrocompatible), comme les chantiers précédents.
- Pas de dépendance ajoutée.
- TDD : tests écrits avant le code, `uv run pytest -m "not integration"` vert, ruff/format/ty propres, `go test ./...` vert dans `sandbox/`.
- Secrets jamais en dur : `SecretStr`, `.env.example` à jour.

## Critères d'acceptation

- [ ] **G1 A2A durci** — `agents/executors.py` passe `tool_policy`, `approval_registry`, `trace_store` à `run_agent` comme `/agent/run` ; le rédacteur wrappe `analysis`/`verdict` avec `wrap_untrusted` ; middleware exige `X-Internal-Token` sur `/api/agents/*` et `/mcp/` quand `INTERNAL_API_TOKEN` est configuré (vide = off), l'orchestrateur interne l'envoie. Tests : executors + middleware + orchestrateur.
- [ ] **G2 HITL** — `ApprovalRegistry` émet un `approval_token` (secrets, usage unique) dans `approval_request` ; `decide` l'exige (401/403 sinon) ; l'endpoint `/agent/runs/{run_id}/approval` et le dashboard le transmettent. MCP : `request_state` = HMAC-SHA256(app_secret_key, payload_hash), vérifié avec `compare_digest`. Tests : registry, endpoint, frontend, MCP elicitation.
- [ ] **G3 Compaction** — le résumé est inséré en rôle `user` (plus `system`) ; `parse_memoires` filtre chaque fait (redaction + scan injection, les bloqués sont lâchés). Tests : compaction.
- [ ] **G4 DoS** — `/market/stream` a `max_duration_s` (défaut 3600, max 86400) ; `/agent/run` et `/api/agents/run` bornés par un `asyncio.Semaphore(3)` (429 si plein) ; `read_pdf` streame le téléchargement avec arrêt à 20 Mo + 1 octet ; sidecar Go : `http.MaxBytesReader` 64 Ko, timeout clampé [1 s, 60 s], kill du pid direct en plus du groupe, filtre seccomp avec check `arch` (x86_64 seul) et rejet du bit x32. Tests : API, pdf (MockTransport stream), Go (`go test`).
- [ ] **G5 Fuite evals** — `.gitignore` couvre `/evals/generated/` (le vrai chemin de sortie), `backend/evals/generated/` retiré. Test : `git check-ignore evals/generated/x` exit 0.
- [ ] `uv run pytest -m "not integration" -q` vert ; `uv run ruff check .` + `ruff format --check` + `uv run ty check` propres ; `cd sandbox && go test ./...` vert.
- [ ] `docs/STATUS.md` et `docs/09-decisions.md` mis à jour (D106+).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agents/executors.py` | policy/approval/trace passés à run_agent ; wrap_untrusted rédacteur |
| `backend/src/investia/main.py` | middleware X-Internal-Token ; semaphore runs ; max_duration_s stream ; approval token ; câblage executors |
| `backend/src/investia/agents/orchestrator.py` | HttpA2ACaller envoie X-Internal-Token |
| `backend/src/investia/agent/approval.py` | approval_token émis/vérifié |
| `backend/src/investia/mcp_server.py` | request_state signé HMAC |
| `backend/src/investia/agent/compaction.py` | résumé en user ; parse_memoires filtré |
| `backend/src/investia/tools/pdf.py` | téléchargement streamé borné |
| `backend/src/investia/config.py` | `internal_api_token: SecretStr \| None` |
| `dashboard/src/api.ts`, `pages/Agent.tsx` | approval_token renvoyé au POST |
| `sandbox/cmd/sidecar/main.go` | MaxBytesReader + timeout clampé |
| `sandbox/internal/sandboxrun/sandboxrun.go` | kill pid + groupe |
| `sandbox/internal/sandboxrun/seccomp_linux.go` | check arch + rejet x32 |
| `.gitignore` | `/evals/generated/` |
| `backend/tests/test_*.py`, `sandbox/*_test.go` | tests TDD |
| `.env.example` | INTERNAL_API_TOKEN |

## Comment vérifier

```bash
uv run pytest -m "not integration" -q   # vert
uv run ruff check . && uv run ruff format --check . && uv run ty check   # propres
cd sandbox && go vet ./... && go test ./...   # vert
cd ../dashboard && npm run test -- --run && npm run build   # vert
```

## Hors périmètre

Les 11 findings low (clés API en query string ×3, tool policy A2A low ×2, injection juge LLM ×2, POST /orders sans token, budget LLM, URL massive, race cash). Le durcissement des clés en header chez les fournisseurs. Toute migration de base.
