# Veille OSS approfondie — 14/11/2026 (2ᵉ passe : 23 harness + écosystème Go + modèle Mistral Timestral)

*Méthode : 10 sous-agents de recherche lancés en parallèle le 14/11/2026 (CLI agents A/B, frameworks A/B, UIs, DeepSeek, transversal, Go libs/agents/infra), recherche web + API GitHub + docs officielles + advisories CVE/GHSA/NVD/OSV, sources d'oct–nov 2026 privilégiées. Lecture seule. Les faits non recoupés sur 2 sources sont balisés ⚠️ dans les rapports d'origine ; ce document ne reprend que les points sourcés. Aucun secret dans ce document.*

## 0. Réponse directe — Mistral Timestral

**Timestral 1.0** = famille de **modèles de fondation pour séries temporelles** (forecasting zero-shot) publiée par Mistral le **15/10/2026** : 4 tailles (**5M / 28M / 123M / 209M** params), inférence **CPU** (< 200 ms), contexte jusqu'à **32K timesteps**, covariables past-only et known-future, sorties probabilistes (quantiles). N°1 des benchmarks GIFT-Eval / TIME / fev-bench parmi les modèles zero-shot pré-entraînés (chiffres Mistral, soumis aux leaderboards, pas encore reproduits indépendamment ⚠️). Poids ouverts sur HF sous **licence « Modified MIT » avec plafond de revenus** (interdit au-delà de 20 M$/mois de revenus — OK pour un projet perso/étudiant).

- **API** : preview publique sur La Plateforme / Mistral Studio (noms type `timestral-1-0-209m`), à moitié prix pendant la preview. Repo OSS : https://github.com/mistralai/timestral (pip install depuis GitHub).
- **Pour Investia** : c'est exactement le type de modèle qu'il manque à un harness financier — un outil `get_forecast(symbol, horizon)` qui prédit la trajectoire d'un cours à partir de l'historique (que `get_history` fournit déjà), avec bandes d'incertitude. Zéro poids à héberger (API) ou à héberger soi-même (CPU, 209M ≈ quelques centaines de Mo).
- **Sources** : https://docs.mistral.ai/models/timestral-1-0-209m · https://docs.mistral.ai/inference/pricing · https://github.com/mistralai/timestral · https://pondero.ai/news/2026-10-17-mistral-timestral-forecasting/ · https://dev.to/gabrielanhaia/mistrals-timestral-runs-on-a-cpu-its-modified-mit-license-stops-at-20m-a-month-141m

## 1. Panorama des harness analysés (données au 14/11/2026)

| Projet | ★ | Licence | Langage | État nov 2026 | Point clé |
|---|---|---|---|---|---|
| openclaw | 394k | MIT | TS (sur pi) | très actif | gateway multi-canaux — **543 CVE trackées** ⚠️, skills ClawHub malveillantes (ClawHavoc) — ne PAS adopter la posture ouverte |
| hermes-agent | 263k | MIT | Python | très actif | boucle d'apprentissage fermée (skills auto-créés), micro-compaction, elicitation MCP routée vers l'UI d'approbation — mais nombreuses CVE 2026 |
| opencode | 227k | MIT | TS | très actif | v2 = service partagé + « Code Mode » (−92 % de contexte MCP), permissions à 2 couches (permissions + policies deny-only) — brèche Console oct 2026, CVE serveur local |
| codex-cli | 135k | Apache-2.0 | Rust | très actif | sandbox OS par défaut (Seatbelt/bwrap+seccomp), double dial approval×sandbox **fail-closed**, compaction server-side à ~90 % — référence sécurité |
| pi | 122k | MIT | TS | très actif | kernel minimal (4 outils), sessions en arbre JSONL forkables, RPC/SDK — YOLO par défaut, pas de sandbox, CVE extensions project-local |
| openhands | 93k | MIT | TS+Py SDK | actif | SDK event-sourcé, condensers enfichables (`POST /condense`), runtimes Docker/SSH — valide notre choix LiteLLM |
| cline | 72k | Apache-2.0 | TS | actif | Plan/Act, checkpoints par étape, CLI headless CI — CLI en « yolo » par défaut ⚠️ |
| crewAI | 61k | MIT | Python | actif | **cluster RCE 2026 confirmé** (CVE-2026-2275/2287/37008, CERT/CC VU#221883) : fallback silencieux vers sandbox faible — la leçon : fail-closed |
| goose | 57k | Apache-2.0 | Rust (AAIF) | actif | 4 modes de permission, recipes, sous-agents héritent des permissions du parent (bug #11778 fixé) |
| aider | 50k | Apache-2.0 | Python | **dormant depuis 05/2026** | repo map tree-sitter + auto-commit git = bonnes idées, projet à ne pas adopter |
| agno | 43k | Apache-2.0 | Python | actif | AgentOS (serving FastAPI clé en main) intéressant — mais CVE-2026-35002 RCE eval() (fix v2.3.24) + issue #10589 ouverte |
| langgraph | ~35-45k | MIT | Python | très actif | checkpointers Postgres, interrupt()/resume HITL typé, time travel — CVE désérialisation checkpoints (CVE-2026-28277) |
| deepagents | ~31k | MIT | Python | actif | harness clé en main au-dessus de LangGraph (planning, FS virtuel, skills lazy, interrupt_on) |
| openai-agents | ~31k | MIT | Python | actif | Sandbox Agents v2, sessions+compaction auto, needs_approval — aucune CVE trouvée ⚠️ |
| qwen-code | 30k | Apache-2.0 | TS | très actif | daemon `qwen serve`, checkpointing auto, auto-memory par projet, `compactionModel` dédié, A2A 1.0 JSON-RPC (PR #12851) |
| smolagents | ~30k | Apache-2.0 | Python | quasi-arrêt | CVE-2026-4963 CVSS 10 (fix incomplet), exécuteur local « not a sandbox » — rien à prendre |
| mastra | 29,5k | Apache-2.0 + ee/ propriétaire | TS | actif | workflows suspend/resume persistés Postgres, streams resumables — supply-chain npm juin 2026 (Sapphire Sleet) |
| crush | 29k | **FSL-1.1-MIT (non OSI)** | Go | très actif | daemon workspace partagé, sessions SQLite, compaction « working set » (PR #4059), 13 hooks dont PreCompact bloquant — **pas de sandbox**, config shell exécutée |
| mini-swe-agent | 9,6k | MIT | Python | calme | boucle ~100 lignes, `cost_limit`/`step_limit` natifs, envs interchangeables (docker/bwrap/Modal), litellm — CVE bwrap sans --clearenv (CVE-2026-108592) |
| pydantic-ai | 21k | MIT | Python | très actif | v2 + harness pkg, DeferredToolRequests/AskUser (HITL in-run), pydantic-evals, AG-UI adapter, OTel v5/Logfire |
| open-webui | 159k | custom (branding) | Python/Svelte | très actif | Tool Approvals + ask_user natifs, MCP apps inline — **pas d'AG-UI natif** |
| librechat | ~45k | MIT | TS | actif | HITL le plus abouti (per-tool Always ask/approve, pause/resume durable ask_user_question), « Prune Mirror » pour le contexte — pas d'AG-UI |
| onyx | ~31k | MIT hors ee/ | Python/Next | actif | Craft = microVMs Firecracker + egress proxy (payant), workflow « CVE Alerts » auto (scan daily + backports) — pas d'AG-UI |
| deepseek-harness (dsh) | 281k | MIT | TS (Cordis) | preview, breaking hebdo | event-sourcing de session, presets permission×approval, PTC — **5+ CVE 2026 dont auth bypass local**, télémétrie vers domaine DeepSeek, pas de mémoire cross-session native → ne pas adopter en l'état |

## 2. Écosystème Go (veille demandée en complément)

- **Frameworks agents Go** : **Eino (CloudWeGo/ByteDance) 13,6k★** leader incontesté (ADK : ReAct, interrupt/resume, checkpoints, MCP, retrievers pgvector) ; ADK Go (Google) 9k★ v2.0 ; Genkit Go 6,6k★ ; trpc-agent-go 1,9k★ ; **langchaingo en maintenance** ; **fantasy (Charm) 1k★** pour CLI. → Aucun ne justifie de porter le harness Python en Go.
- **MCP en Go** : SDK officiel `modelcontextprotocol/go-sdk` v1.8.0 (Tier 1, spec 2026-07-28, OpenSSF) préféré à `mcp-go` v1.5.0 (4 CVE 2026 : CVE-2026-123272 OAuth critique, CVE-2026-108859 DoS, CVE-2026-81092 DNS rebinding). Règle : go-sdk ≥ v1.8.0, mcp-go ≥ v1.5.0. `googleapis/mcp-toolbox` (16,9k★) expose Postgres/pgvector en MCP zéro code.
- **Gateway LLM Go** : **Bifrost (maximhq) 9,5k★**, Apache-2.0, ~11 µs @ 5000 RPS (~50× LiteLLM en P99), semantic cache, budgets, MCP gateway — meilleure piste si LiteLLM atteint ses limites.
- **Infra** : pgx v5.13 (CVE SQLi protocole simple → rester ≥ v5.9.2), OTel Go v1.47 (semconv GenAI), Temporal sdk-go v1.51, Watermill v1.5.3, valkey-go si migration Valkey 9.x.
- **Sandbox** : consensus 2026 = **nsjail** (0 CVE connue, process-level), **gVisor/runsc** (donné à la CNCF le 06/11/2026 avec « Agent Substrate »), **Firecracker** (microVM, mais CVE 2026 actives → ≥ 1.15.1). Un **sidecar Go de sandboxing** (binaire statique spawné par le harness Python) est la seule brique Go vraiment pertinente.
- **Sources** : rapports des agents veille-go-libs / veille-go-agents / veille-go-infra (URLs dans leurs rapports).

## 3. Tendances transversales nov 2026 (ce que tout l'écosystème fait)

1. **Fail-closed partout** : si le sandbox ne peut pas s'appliquer, on refuse d'exécuter (Codex) ; timeouts d'approbation → deny (OpenClaw 2026) ; CrewAI a supprimé purement son CodeInterpreterTool plutôt que de patcher. Leçon CVE-2026-19593 : protéger la config git/hooks des dépôts ingérés. Approbations scopées aux **arguments**, pas seulement au chemin (CVE-2026-100560).
2. **Compaction non destructive** : « stamp, don't delete » (opencode `compacted=<ts>`), checkpoints provider, re-jeu du dernier message user, pré-calcul de résumés en arrière-plan ; crush travaille sur un « working set » verbatim + hook `PreCompact` bloquant ; codex préserve les messages user verbatim. Hermes : micro-compaction + cooldown d'échec persisté.
3. **Tool policy AVANT l'appel modèle** : si une policy retire un outil, le modèle ne reçoit pas son schéma (OpenClaw) — plus fort qu'un garde-fou post-hoc.
4. **Protocoles** : **AG-UI 1.0** stable (30/09 puis 11/11/2026, CopilotKit) — adopté par LangChain/PydanticAI/ADK/Mastra/CrewAI/AG2/Strands/Agno… mais **aucune UI self-hosted généraliste** (OpenWebUI/LibreChat/Onyx n'ont que des feature requests) → notre implémentation AG-UI maison reste différenciante. **A2A v1.0** (mars 2026, passé à l'AAIF août 2026, cards signées JWS) adopté par Agno v3.2, qwen-code, hermes, openclaw. **ACP** = standard IDE (Zed/JetBrains), v2 draft juillet 2026. **MCP 2026-07-28** : cœur stateless, MRTR, elicitation conservée pour le HITL.
5. **Coût** : même modèle, coût jusqu'à 5× selon le harness (étude Berkeley sept 2026) ; règle « préserver le cache » dans les routeurs (opencode v2.2.7) ; LiteLLM v1.101 ajoute le routage par complexité natif côté gateway.
6. **Sécurité 2026** : vague de CVE sur tous les harness CLI (opencode serveur local, dsh auth bypass, codex sandbox escapes sept 2026, openclaw 543 CVE ⚠️, hermes, cline…) ; supply-chain npm/GitHub Actions massive (Mastra juin 2026, GhostAction oct 2026) → **provenance/lockfile vérifiés obligatoires** ; skills/extensions = menace n°1 (ClawHavoc : 341 skills malveillantes/2857 auditées).
7. **Evals de harness en CI** : pattern marmelab « figer tâches → run bout en bout → scorer » ; harness-evals, pydantic-evals (ToolCorrectness, TrajectoryMatch), cline/harbor.
8. **Modèles** : DeepSeek V4.1-Flash-1017 (MIT, 1M tokens, cache hit ~50× moins cher, off-peak −50 % sur ~21 % de la semaine) routable via LiteLLM (`deepseek/` + alias `-latest`) — candidat tier « petit modèle » crédible ; ban fédéral US 20/10/2026 (données en Chine) → garder la redaction PII en amont quel que soit le modèle. Mistral Large 4 (1T params) en preview API.

## 4. Top 10 des idées adoptables pour Investia (classées)

1. **Outil `get_forecast` avec Timestral** (API Mistral via LiteLLM ou appel direct) : prévision de cours avec bandes d'incertitude à partir de `get_history` — cas d'usage financier natif, zéro hébergement. (Chantier 17a.)
2. **DeepSeek Flash comme tier « petit modèle » du routeur** via LiteLLM (`deepseek/deepseek-flash-latest`) : cache serveur + fenêtre off-peak pour lancer les evals batch et la compaction en heures creuses. Gotcha `reasoning_content` à tester dans nos evals. (17b.)
3. **Fail-closed du sandbox `run_python`** : si le backend sandbox (nsjail/sandbox-exec) est indisponible → lever une erreur et stopper le run, jamais de fallback local ; watchdog de vivacité. Leçon CrewAI CVE-2026-2287. (17c.)
4. **Compaction « working set » + hook PreCompact bloquant** (crush PR #4059 + hooks) : garder un tail verbatim + chemins/erreurs exacts, et permettre au HITL hashé de veto la compaction. (17d.)
5. **Tool policy pré-schéma** (OpenClaw) : un outil retiré par policy n'est pas envoyé au modèle (pas de schéma) — à appliquer au-dessus de nos garde-fous/permissions. (17e.)
6. **Double dial approval × sandbox** (Codex) : séparer « quoi » (approval policy) de « où » (sandbox mode), refuser d'exécuter si le sandbox ne peut pas s'appliquer. (17e, même chantier.)
7. **Routeur : règle « préserver le cache »** (opencode v2.2.7) + coût/run exposé + budget caps au niveau gateway LiteLLM. (17f.)
8. **Elicitation MCP : refuser les URL-mode, router les form-mode vers la surface d'approbation** (hermes) — extension de notre 15a. (17g.)
9. **SSRF : étendre le blocage RFC1918/loopback aux callbacks push A2A et fetchs médias** (hermes security docs). (17g, même chantier.)
10. **Workflow « CVE Alerts » automatisé** (Onyx) : scan daily des lockfiles + images, issue/PR auto, backport — pour tout le repo. (17h.)

## 5. Ne PAS adopter (et pourquoi)

- **dsh (deepseek-harness)** en l'état : preview, breaking hebdo, SAFETY.md « not production-ready », 5+ CVE dont auth bypass du control plane local, télémétrie vers DeepSeek, pas de mémoire cross-session native, pas d'A2A/AG-UI. Patterns à copier seulement : event-sourcing append-only + compaction par nœud résumé ; séparation permission preset × approval policy.
- **CrewAI / Agno / smolagents / aider / crush (code)** : CVE RCE 2026 (CrewAI cluster, Agno eval, smolagents fix incomplet), projet dormant (aider), licence FSL non OSI (crush).
- **OpenClaw** : posture gateway ouverte, 543 CVE trackées ⚠️, ClawHavoc — ne jamais exposer de canal externe sans signature des skills.
- **Aucune brique Go** dans le cœur (agent loop, DB, LLM) — Python en avance ; seul un **sidecar Go de sandboxing** (nsjail) est une piste valable, et **Bifrost** si LiteLLM limite en perf.
- **UIs généralistes** (OpenWebUI/LibreChat/Onyx) : aucune ne fait AG-UI natif — notre dashboard + AG-UI maison reste devant.
- **jina-embeddings** (CC-NC), **Daytona/E2B/PyRIT/HumanLayer** (SaaS ou hors besoin) — déjà tranché dans la veille du 14/11.

## 6. Watchlist sécurité (à intégrer au rythme de patch)

pgx ≥ v5.9.2 (SQLi protocole simple) · OTel-Go ≥ v1.47.0 · mcp-go ≥ v1.5.0 / go-sdk ≥ v1.8.0 (DNS rebinding, OAuth, DoS) · gVisor ≥ commit 573a9e73 (CVE-2026-96812) · Firecracker ≥ 1.15.1 · LiteLLM ≥ v1.109.1 (backdoor v1.82.x CVE-2026-33634 au CISA KEV, déjà noté) · langgraph-checkpoint ≥ 3.1.3 (CVE-2026-28277/115883) si jamais adopté · supply-chain : lockfiles + provenance (Mastra juin 2026, GhostAction oct 2026).

---

*Rapports détaillés des 10 sous-agents : conservés dans la session (lecture seule, aucun fichier projet modifié pendant la veille). Ce document est la version consolidée et citable.*
