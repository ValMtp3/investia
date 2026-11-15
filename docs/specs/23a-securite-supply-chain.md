# Spec 23a — Sécurité supply-chain (pins CVE 2026 + scan MAL automatisé)

> Chantier 23a, issu de la veille OSS du 15/11/2026 (`docs/veille-oss-2026-11-15.md`, D94).
> Contexte : plusieurs CVE/backdoors de 2026 nous visent directement. Constats à date
> (vérifiés dans le repo le 15/11) :
> - image litellm **déjà** `ghcr.io/berriai/litellm:v1.109.1` (backport sécu #51254) — mais
>   pin par version seule, pas de digest ;
> - image pgvector `pgvector/pgvector:pg17` **non pinnée** (tag flottant) — CVE-2026-103484
>   (RCE via build IVFFlat, pgvector ≤ 0.8.6, CVSS 8.8) nous concerne (mémoire + routeur k-NN) ;
> - react/react-dom **déjà** 19.3.1 (package.json `^19.3.1`, lockfile 19.3.1) — CVE-2026-126187
>   (RCE RSC, fix 19.3.1) couverte, à verrouiller par un test ;
> - certifi **déjà** 2026.10.23 dans `uv.lock` (≥ 2026.10.19 requis, CA eMudhra CVE-2026-115557) ;
> - fastmcp 4.2.0 / mcp 2.3.0 dans `uv.lock` (CVE MCP 2026 couvertes côté SDK) ;
> - workflow `cve-alerts.yml` (17h, trivy v0.67.2 daily) couvre les vulnérabilités mais
>   **pas les paquets malveillants** (entrées OSV `MAL-`, ex. litellm 1.107.0 du 21/10/2026).

## Objectif

Verrouiller par des **tests + du CI** ce qui est déjà en place, pinxel les images flottantes,
et ajouter un scan OSV (incl. MAL) automatisé.

## Contrat détaillé

### 1. Pin pgvector — CVE-2026-103484 (RCE, nous concernés)

- Remplacer `pgvector/pgvector:pg17` par `pgvector/pgvector:0.8.7-pg17` (tag vérifié sur
  Docker Hub le 15/11, poussé par ankane) dans :
  - `deploy/docker-compose.yml`, `deploy/docker-compose.prod.yml` ;
  - `.github/workflows/ci.yml` (service postgres du job pytest) ;
  - `deploy/backup/test_backup.sh`.
- Test (`test_deploy.py`) : l'image pgvector match `pgvector/pgvector:(\d+)\.(\d+)\.(\d+)-pg17$`
  avec version ≥ 0.8.7.

### 2. Test image litellm — backdoors 2026

- Test (`test_deploy.py`) : l'image litellm est `ghcr.io/berriai/litellm:vX.Y.Z` avec
  (X,Y,Z) ≥ (1,109,1) et version ∉ {1.82.7, 1.82.8, 1.107.0} (backdoors TeamPCP / oct-2026).
- La vérification **cosign + digest `@sha256:`** reste une procédure owner (documentée dans
  `docs/verifs-live-vps-2026-11-15.md`), pas en CI.

### 3. Tests lockfiles — régressions pinnées (nouveau `backend/tests/test_supply_chain.py`)

- `uv.lock` : `certifi` ≥ 2026.10.19 (eMudhra) ; `fastmcp` ≥ 4.2.0 ; `mcp` ≥ 2.3.0 (CVE MCP 2026).
- `dashboard/package-lock.json` : `react` et `react-dom` ≥ 19.3.1 (CVE-2026-126187).
- Parsing stdlib (`tomllib` pour uv.lock, `json` pour package-lock), zéro dépendance.

### 4. Workflow `cve-alerts.yml` — job OSV/MAL

- Nouveau job `osv` : binaire **osv-scanner v2.7.1** épinglé (release GitHub, même pattern
  d'installation que trivy), scan de `backend/uv.lock` et `dashboard/package-lock.json`,
  `--exit-code 1` sur **tout** finding (les entrées `MAL-` = paquets malveillants sont incluses
  dans la base OSV), artifact `osv-lockfiles.json` uploadé.
- Le job `alerte` (ouverture d'issue auto) déclenche aussi sur `needs.osv.result == 'failure'`
  (`needs: [lockfiles, images, osv]`).
- Test statique (pattern `test_deploy.py`) : le YAML parse, le job `osv` existe, la version
  d'osv-scanner est épinglée (regex `v\d+\.\d+\.\d+`), `alerte` inclut `osv` dans ses `needs`.
- ⚠️ Comme en 17h : actionlint non dispo en local — le run réel du workflow sera vérifié via
  Actions (workflow_dispatch) après merge.

### 5. Docs

- `docs/STATUS.md` : entrée 23a + cocher l'item litellm de la checklist VPS (version déjà
  v1.109.1 ; il reste digest+cosign côté owner).
- `docs/09-decisions.md` : D95.
- `docs/verifs-live-vps-2026-11-15.md` : mise à jour de la section 1 (bump déjà fait,
  reste la vérification cosign/digest + rotation des clés si une version compromise a tourné).

## Tests (TDD)

1. `test_deploy.py` : pgvector pinné ≥ 0.8.7 ; litellm ≥ v1.109.1 et hors versions malveillantes.
2. `test_supply_chain.py` (nouveau) : certifi / fastmcp / mcp dans uv.lock ; react / react-dom
   dans package-lock.json.
3. `test_deploy.py` (suite) : workflow cve-alerts.yml — job `osv` présent, version épinglée,
   `alerte.needs` contient `osv`.

## Fichiers touchés

- `deploy/docker-compose.yml`, `deploy/docker-compose.prod.yml`, `deploy/backup/test_backup.sh`
- `.github/workflows/ci.yml`, `.github/workflows/cve-alerts.yml`
- `backend/tests/test_deploy.py`, `backend/tests/test_supply_chain.py` (nouveau)
- `docs/STATUS.md`, `docs/09-decisions.md`, `docs/verifs-live-vps-2026-11-15.md`, cette spec

## Critères d'acceptation

- Suite non-integration verte, ruff/format/ty propres, CI verte (tous jobs, y compris la
  modification de cve-alerts.yml parsée OK).
- pgvector pinné 0.8.7-pg17 partout ; aucun tag flottant restant sur nos images.
- Le scan OSV/MAL tourne en daily + dispatch et ouvre une issue en cas de finding MAL.

## Hors périmètre

- Digest `@sha256:` des images en CI + cosign verify automatisé (procédure owner documentée).
- Rotation des clés providers (owner, si une version compromise a tourné sur le VPS).
- mcp-scan (outil client-side ; notre serveur FastMCP n'expose pas OpenAPIProvider).
- Bump trivy, migration vers Bifrost, pin Node/uv/pip globaux (hors repo).
