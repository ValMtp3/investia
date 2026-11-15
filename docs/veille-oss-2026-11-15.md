# Veille OSS consolidée — 15 novembre 2026

Rapport demandé par le propriétaire : veille fraîche depuis celle du 14/11/2026 (`docs/veille-oss-2026-11-14.md` + `-approfondie.md`), pour savoir ce qui a bougé et quoi adopter ensuite.

**Méthode** : 8 sous-agents de recherche lancés en parallèle le 15/11/2026 ~10:56 UTC — (1) harness & CLI de coding, (2) evals & observabilité, (3) protocoles multi-agents 2026, (4) sécurité/sandbox/CVE, (5) routage & coût & nouveaux modèles, (6) mémoire & contexte, (7) frontend React 19, (8) écosystème Go. Canaux : API GitHub publique, PyPI/npm, Hugging Face Hub, OSV, arXiv, blogs officiels, HN/Reddit. Chaque finding du rapport d'origine est tagué VÉRIFIÉ (release taguée / CVE OSV / artefact daté) ou BLOG ; ici seuls les éléments recoupés ou vérifiés sont repris. Aucun secret dans ce document. Aucune dépendance ajoutée (règle du projet).

## Réponse directe : est-on toujours au niveau ?

Oui sur le cœur. Aucun framework OSS de novembre 2026 ne domine ni ne casse notre avantage (garde-fous en code + HITL deny-by-default + sandbox fail-closed + traces Postgres + evals maison + routeur k-NN appris). Les nouveautés réelles depuis le 14/11 sont : le protocole **A2UI 1.0** (Google, 11/11), une **alerte supply-chain majeure sur notre gateway LiteLLM** (2 backdoors en 2026, dont une en octobre) + une CVE RCE **pgvector** qui nous concerne directement, et la confirmation que la **compaction/contexte** est le chantier n°1 de l'industrie (nous sommes déjà au niveau avec 17d).

## 🔴 Urgent — sécurité supply-chain (nos propres dépendances)

| Finding | Détail | Action |
|---|---|---|
| **LiteLLM backdooré 2× en 2026** [VÉRIFIÉ OSV] | `1.82.7/1.82.8` (24/03, TeamPCP via Trivy compromis CVE-2026-33634) et `1.107.0` (21/10, MAL-2026-2144, credential stealer + RCE exécuté à chaque démarrage Python). Nous sommes en **v1.106.5** : non touchée par l'incident d'octobre, mais la gateway détient **toutes les clés providers** = cible n°1. + GHSA-7hp6-4w63-5g45 (CVSS 9.9, escalade internal_user→proxy_admin) et GHSA-g5ff-637f-6q2m (8.1, lecture `/proc/self/environ` → master key) → `internal_user_viewer` off. + CVE-2026-89032 : le cache sémantique LiteLLM fuit cross-user → namespacer par user/session. | Bump **≥ v1.108.9** (LTS 14/11) ou **v1.109.1** (12/11, backport sécu #51254), image épinglée **par digest + cosign vérifié**, jamais `latest`, scan OSV/MAL en CI sur le lockfile, rotation des clés si une version compromise a tourné. |
| **pgvector CVE-2026-103484** [VÉRIFIÉ OSV, CVSS 8.8] | out-of-bounds write au build d'index **IVFFlat** → RCE, toutes versions ≤ 0.8.6. **Nous sommes concernés** (mémoire pgvector + routeur k-NN 12h/18a). | Upgrade extension **≥ 0.8.7** sur le Postgres VPS dès que possible. |
| **React CVE-2026-126187** [VÉRIFIÉ OSV, CVSS 9.5] | RCE non authentifiée React Server Components, fix 19.0.9/19.1.10/19.2.9/**19.3.1** (10/11). Notre dashboard est une SPA Vite (pas de RSC) → non exposé directement, mais le lockfile doit être vérifié. | Bump react/react-dom **≥ 19.3.1** (nous sommes en 19.x). |
| **CA eMudhra/emSign compromis (22/10/2026)** [VÉRIFIÉ] | trust-store à jour : certifi ≥ 2026.10.19, pip 26.2.2, uv 0.13.4, Node 22.23.4/24.22.1 (CVE-2026-115557). | Pin `certifi>=2026.10.19` dans nos environnements. |
| **6 CVE récentes écosystème MCP** [VÉRIFIÉ OSV] | redirects cross-origin suivis avec headers custom (TS fixed 1.32.0 / client 2.3.0 ; PyPI fixed 1.30.1+), OAuth `issuer` (CVE-2026-104850), `$ref` serveur = SSRF (CVE-2026-116686), fuite cross-client (fixed 1.26.0), audience bearer. MCP devient **CNA** (SEP-3543, PR ouverte 15/11) → plus de CVE MCP à venir. | Pins SDK patchés, **mcp-scan v0.6.11 en CI** sur nos serveurs/configs MCP, ne jamais suivre de redirect cross-origin, valider issuer/audience. |

## Shortlist consolidée (classée par domaine)

### 1. Protocoles — A2UI 1.0, le vrai nouveau de novembre
- **A2UI 1.0** (Google, 11/11/2026, Apache-2.0, repos `google/A2UI` / `a2ui-project/a2ui`) : protocole agent→UI **déclaratif** — l'agent décrit l'UI (surfaces, composants, data-binding serveur), le client rend avec **son propre catalogue de composants whitelisté**. Data-binding côté serveur = les valeurs sensibles n'atteignent pas le modèle. Ponts prêts : `@ag-ui/a2ui-middleware@0.0.16` (12/11), `@copilotkit/a2ui-renderer@1.88.0` (13/11). Adoptants : Atlassian, Bloomberg, ByteDance. **Décision : ADOPTER en complément d'AG-UI** (pas en remplacement) — notre whitelist `ui_component` (21b) se transpose naturellement en catalogue A2UI. Risques : valider contre le schéma, jamais de HTML/MDX brut, DSL/Macros exécutés en sandbox uniquement.
- **A2A** : spec v1.0.1 stable ; **v1.1.0-rc** en préparation (AI Catalog `ai-catalog.json`, SendLiveMessage bidirectionnel, resumption) → VEILLE jusqu'à la GA, préparer la publication publique. SDKs py/js v1.3.0, rien depuis le 14/11. Garder nos cards **JWS signées**.
- **MCP spec 2026-07-28** : migration **stateless + MRTR (SEP-2322 Final)** à notre prochaine fenêtre — notre elicitation form-only reste valide mais en *in-call*. Registry officiel **v1.8.9** (10/11) → y publier nos serveurs. **FastMCP v4.2.0** (13/11, skills over MCP SEP-2640 beta) → upgrade contrôlé. **SEP-2848** (approval asynchrone des tool calls = HITL standardisé) → VEILLE, très proche de notre deny-by-default.
- **ACP v1.18.0** (14/11, Zed/JetBrains) : protocole éditeur↔agent de code → VEILLE (un endpoint serveur ACP optionnel pour piloter Investia depuis un IDE ; notre dashboard AG-UI couvre déjà le besoin). Lire les Additional Terms.
- **AGNTCY DIR v1.9.0 / ARD / AITP (draft) / SLIM (MLS post-quantique)** → VEILLE (pertinent si publication publique cross-org ; nos cards JWS couvrent l'essentiel). **NE PAS ADOPTER** : OpenA2A (drafts IETF, écosystème mince), PharmA2A, Personal Agent Protocol.

### 2. Harness & CLI de coding — tendances de fond confirmées
- **Équipes de subagents async par défaut** : opencode v2.3.0 (13/11), crush v0.100 (teams), DeepSeek DSH AgentTeam, qwen-code `runAgentLoop`. → valide notre A2A ; **prochaine étape** : rendre le retour des sous-agents A2A async par défaut.
- **Compaction = chantier n°1 de novembre** : OpenClaw beta.3 (15/11, « pre-compaction memory flush » — **déjà implémenté chez nous** en 17d), goose v1.59 (context relevance + viewer), arXiv 2611.05306 (compaction fréquente > long contexte), CompactionBench (Microsoft). → nous sommes au niveau (working-set 17d) ; il manque le **viewer/debug de contexte** et des **métriques de compaction** dans nos evals.
- **Fallback multi-providers résilient** (hermes canary 15/11) → valide notre routeur k-NN + LiteLLM ; valider la route résolue (endpoint+query) avant exécution.
- **Gaps interop** : format **Agent Skills** cédé à l'AAIF (agentskills.io, 22/10) et **ACP v2** (Copilot, Zed, DSH, opencode) → à adopter pour l'interop éditeur/CLI.
- **NE PAS ADOPTER** : OpenClaw tel quel (chaîne de CVE 2026 ClawHavoc/Claw Chain, gateway multi-canaux = surface d'attaque), crush (pas de sandbox + licence FSL non OSI), mini-swe-agent (dormant), langchaingo (congelé), Roo Code (archivé 15/05/2026), Continue (mort juin 2026).

### 3. Evals & observabilité
- **Harbor + Terminal-Bench continu** : TB 4.1 (datasets **pinnés par version**, verifiers anti-reward-hacking), TB-Science 0.1, arXiv 2611.08417 (« benchmarks as software »). → **ADOPTER Harbor comme benchmark externe** de notre agent conteneurisé (notre runner mock/live 22a reste la source de vérité produit). Ne plus gater sur SWE-bench Verified (saturé ~95 %, contaminé — SWE-rebench : 39,7 % → 21,3 % sur tâches fraîches).
- **Pattern dataset pinning + changelog** (Langfuse `dataset_version`) → à coder dans notre runner 22a (on a déjà le dataset depuis traces).
- **LLM-as-judge 2026** : biais documentés (arXiv 2611.04090 : changer de juge change le ranking ; 2610.12083) ; règle maison : déterministe d'abord, juge calibré + position-swap + span-id cité. **JevEval/Jev** (DeepEval) = juge déterministe 37× moins cher (arXiv 2610.18122) → à évaluer.
- **Métriques tool correctness / trajectoires** : audit 2026 = 18,5 % de désaccord évaluateur auto vs humain (brittle state matching, trajectory lock-in) → construire maison : tool-set match sans lock-in, partial credit step-level, validation contre un échantillon humain.
- **garak v0.17.1** (NVIDIA, Apache-2.0) en job CI sécurité isolée (probes injection/jailbreak) ; **promptfoo** (acquis par OpenAI 03/2026, MIT promis — surveiller) pour le red-team agent en CI pinnée, jamais en prod. **NE PAS ADOPTER** : Braintrust/LangSmith/Opik SaaS (vos traces partent chez le vendor) ; aucun gateway vendor dans le chemin d'inférence (SPOF runtime).
- Phoenix v21.1.0 (13/11, ELv2) / Langfuse v4.80.0 (13/11, MIT mais 4 services self-host) → VEILLE ; nos traces Postgres + OTel maison restent au niveau. OTel GenAI semconv toujours en statut « development » → épingler la version.

### 4. Routage, coût & nouveaux modèles
- **Routeur k-NN pgvector (12h/18a)** — quoi ajouter : (1) **LinUCB / ε-explore** au-dessus du k-NN (pattern OrcaRouter arXiv:2605.30736) avec anti-windup (boucle fermée stable) ; (2) **features coût/heure** (off-peak DeepSeek −50 % hors 01:00–04:00 & 06:00–10:00 UTC lun–ven) et coût prédit par requête ; (3) **calibration du seuil vs budget** hors-ligne sur le **dataset 22a** (RouterArena ICLR 2026 comme scorer externe, arXiv:2510.00202) ; (4) cache sémantique **namespacé par user**, seuil ≥ 0,9, error budget (CVE-2026-89032, arXiv:2601.23088/2611.02498) ; (5) index **HNSW** plutôt qu'IVFFlat (latence + la CVE pgvector ci-dessus).
- **Prompt caching structuré** : prefix stable (system + contexte), `cache_control` sur les blocs longs (Anthropic write 1,25×/read 0,1× ; auto-cache OpenAI/DeepSeek ≥ 1024 tokens) ; **Batch API −50 %** pour tout ce qui n'est pas temps réel (evals, rapports, dataset 22a).
- **Nouveaux modèles nov 2026** : Mistral Large 4 (1T-A52B, poids 05/11, Modified MIT — déjà notre « large »), DeepSeek V4.1-Flash-1017 (MIT, off-peak −50 % — déjà notre tier « small » 17b), **Qwen3.8-27B** (Apache-2.0, candidat self-host mid-tier), GLM-5.3, MiniMax M3.1-Flash ($0,15/$0,60), Inkling-2-Small (Apache-2.0 mais 394 Go). **Kimi K3 / Timestral = licence non OSI** → API seule / veille juridique. Ne jamais charger les poids « heretic/uncensored » qui pullulent sur HF (repos officiels uniquement).
- **Bifrost v2.5.1** (Go, Apache-2.0, 10/11) → plan B gateway si LiteLLM déraille (semantic cache, MCP Code Mode) ; VEILLE sinon.

### 5. Mémoire & contexte
- **Schéma bi-temporel maison** (à construire sur notre mémoire pgvector) : `valid_at`/`invalid_at` + `source_id`/provenance + règle **supersede-pas-reject** (invalider l'ancien, jamais de rejet silencieux — bug documenté mcp-memory-service v12.10.0, 14/11). Aucun lib standard ne s'impose en SQL pur → maison.
- **Harrier-OSS-v1-270m** (Microsoft, MIT, ONNX int8 publié 06/11) → benchmarker contre notre embedding local (16b/16c) sur un jeu FR/finance maison.
- **LongMemEval-S** comme eval régulière de la mémoire (mock d'abord) + un **mini-Bemula** pour l'oubli/suppression (RGPD — arXiv 2610.18052 : aucun système testé ne satisfait > 1,5 % des demandes d'oubli).
- **Sécurité mémoire** : memory poisoning = nouvelle catégorie OWASP (05/2026) ; MemCut arXiv 2610.21405 (secrets persistants) → **scrub des secrets avant écriture mémoire**, mémoire = donnée non fiable (règle existante), quarantaine des contradictions.
- Contexte : compaction fréquente + retrieval plutôt que stuffing (arXiv 2611.04169 : c'est la **compétition** entre évidences contradictoires qui dégrade, pas la longueur) → déjà alignés.

### 6. Sécurité de la boucle (au-delà du supply-chain)
- **Guard d'injection sur les tool outputs** : `Horizon-Labs/prompt-injection-guard-small` (140 M, Apache-2.0, ONNX CPU, maj 09/11, entraîné sur Nemotron indirect-injection + llmail) → **filtre dur avant réinjection dans le contexte**, en complément du juge LLM. Alternative récente : wolf-defender v2.1 (14/11). `llm-guard` archivé 07/2026 → ne pas adopter.
- **SSRF** : notre guard 17g couvre la résolution ; il manque le **pinning IP à la connexion** (ferme le DNS rebinding) + re-check dans le hook DNS + guard egress **unique** pour tous les outils (CVE-2026-55525 PraisonAI : bypass quand chaque outil a son helper).
- **HITL durci** : **hash SHA-256 du payload approuvé** affiché à l'humain, stocké en trace, re-vérifié avant exécution (anti-TOCTOU « replan-after-yes ») → construire maison ; Cedar v4.14.1 en évaluation pour la policy (preuve formelle).
- **Canary tokens** maison (un token par outil réseau, détection dans les traces Postgres + alerte) ; spotlighting conscient de son bypass adaptatif.
- **Presidio 2.2.366** (27/10) + **gitleaks v8.30.1** en pre-commit/CI sur le repo **et** les traces exportées (PII/secrets hors Postgres/OTel).
- **Sandboxing OS** : nsjail 3.6 / **Anthropic sandbox-runtime v0.0.83** (12/11, choisit le meilleur backend seatbelt/landlock/bwrap/nsjail) → couche d'abstraction au-dessus de notre fail-closed ; microVM (libkrun v1.19.8, e2b self-host, microsandbox v0.7.15) → VEILLE (coût/ops sur VPS mono-tenant) ; **NVIDIA OpenShell v0.1.8** (10/11) → VEILLE active (jeune).

### 7. Frontend dashboard (DA D63 inchangée)
- **streamdown 2.7.1** (Vercel, Apache-2.0) → **ADOPTER** pour remplacer notre renderer markdown maison : streaming (remend), sanitize (rehype-sanitize + rehype-harden), rendu AST→JSX (pas de `dangerouslySetInnerHTML`). Risque : highlighter/Mermaid chargés via CDN en v2 → `cdnUrl` épinglé + SRI + CSP.
- **Patterns shadcn AI Elements** (Trace pour /traces, Confirmation pour le HITL) → copier le code (zéro dep) ; **NE PAS installer** le package `ai-elements` (déprécié fin 11/2026).
- **React 19.3.1** (bump CVE ci-dessus) : `<Activity>` pour garder montés les panneaux chat/traces, View Transitions, Trusted Types. React Compiler via **oxc** (Vite 8 / plugin-react v6), pas Babel.
- **SSE** : `id:` croissant par run + **Last-Event-ID honoré avec replay depuis Postgres** (nos traces), client **fetch-based** (EventSource natif n'accepte pas le header Authorization), heartbeats + `X-Accel-Buffering: no`.
- **A11y du streaming** : une **seule live region** en fin de DOM, annonces début/fin de réponse (jamais `aria-live` par message — cacophonie NVDA).
- **XSS sortie LLM** : CVE-2026-42045 (LobeChat, XSS→RCE) et série Open WebUI 2026 → AST→JSX uniquement, CSP prod + Trusted Types, blocage SVG/iframe. DOMPurify ≥ 3.4.18 (14/11) si HTML ponctuel — insuffisant seul (bypass récurrents).
- **@ag-ui/client 1.0.4** + resume applicatif (threadId/runId + event log Postgres — AG-UI ne replaye pas seul). **lightweight-charts 5.3.0** (10/11) + plugins officiels. TanStack AI 1.4.0 → VEILLE.

### 8. Écosystème Go (demande explicite du propriétaire)
- **D41 confirmé chiffré** : cœur en Python, Go pour un composant chaud uniquement (notre mesure P7 : `apply_order` Python 559,6 ns/op vs Go 10,3 ns/op = **54,3×**). Aucun framework Go (eino v0.9.23, ADK Go v2, Genkit 1.14, trpc-agent-go) n'apporte nos garde-fous en code → ne pas porter le harness en Go.
- **La seule brique Go mûre à adopter** : un **sidecar de sandboxing** (binaire statique spawné par le harness Python, subprocess fail-closed — notre design actuel) : **sandlock-go / nono** (Landlock+seccomp, fail-closed, Linux ≥ 6.12) en local, **gVisor + Agent Substrate 1.0** (donné à la CNCF, KubeCon NA 11/2026) sur le VPS Docker.
- Si composant Go : **Go ≥ 1.27.3** (15 CVE en 1.27.2, eMudhra en 1.27.3), PQ TLS par défaut (Go 1.26+), `runtime/secret` pour les clés, json v2 (1.27).
- **MCP en Go** : préférer le **go-sdk officiel ≥ v1.8.0** (Tier 1) à mark3labs/mcp-go v1.5.0 (3 CVE 2026 actives) ; pattern « stateless 2026-07-28 » à imiter côté Python.
- **A2A en Go** : a2a-go v2.8.0 (06/11) si un agent Go rejoint le mesh (executor ACP→A2A).
- Patterns à imiter : HITL typé resumable (Genkit 1.14 `DefineResumableTool`), checkpoints imbriqués (eino v0.10-alpha), MCP Tasks replay-safe (trpc-agent-go).

## À NE PAS adopter (vérifié le 15/11/2026)

OpenClaw tel quel (CVE 2026 en chaîne, gateway exposé) · crush (pas de sandbox, licence FSL non OSI) · llm-guard (archivé 07/2026) · mini-swe-agent (dormant) · langchaingo (congelé) · Roo Code (archivé 15/05/2026) · Continue (mort 06/2026) · ai-elements npm (déprécié fin 11/2026) · react-financial-charts (stale 2023) · nomic-embed-text-v2 (n'existe pas — rumeur) · poids « heretic/uncensored » sur HF · Braintrust/LangSmith/Opik/Braintrust SaaS (traces chez le vendor) · gateways vendor dans le chemin d'inférence (SPOF) · OpenA2A / PharmA2A / Personal Agent Protocol · OpenShell tant que v0.1.x · e2b/microsandbox en prod sur VPS mono-tenant · Kimi K3 / Timestral en self-host (licence non OSI) · SWE-bench Verified comme gate (saturé/contaminé).

## Shortlist proposée pour le prochain chantier (à trancher avec le propriétaire)

1. 🔴 **Sécurité supply-chain** : bump litellm ≥ v1.108.9 (digest+cosign), react ≥ 19.3.1, pgvector ≥ 0.8.7, pin certifi ≥ 2026.10.19, scan OSV/MAL automatisé en CI, mcp-scan en CI.
2. 🔴 **Boucle** : guard egress unique avec pinning IP + hash SHA-256 sur chaque approval HITL + prompt-injection-guard-small sur les tool outputs + canary tokens.
3. 🟠 **A2UI 1.0** en complément d'AG-UI (catalogue de composants whitelisté côté renderer).
4. 🟠 **Routeur** : LinUCB/ε-explore + features coût/heure + calibration seuil vs budget sur le dataset 22a + cache sémantique namespacé.
5. 🟠 **Mémoire bi-temporelle** (valid_at/invalid_at + supersede) + LongMemEval-S en eval + mini-Bemula (oubli) + scrub secrets (MemCut).
6. 🟡 **Frontend** : streamdown 2.7.1 + SSE Last-Event-ID/replay + une live region a11y + shadcn Trace/Confirmation copiés.
7. 🟡 **Evals externes** : Harbor + Terminal-Bench 4.1 pinné + dataset pinning dans le runner 22a + garak en CI.
8. 🟡 **Go** : sidecar de sandboxing (sandlock-go local / gVisor VPS) — seul composant Go justifié.
